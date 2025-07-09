import os
import logging
import secrets
from django.db import transaction
from decimal import Decimal
from django.urls import reverse_lazy
from django.contrib.messages import success
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, get_object_or_404
from django.views.generic import DetailView, CreateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.edit import UpdateView
from django.conf import settings
from django_tables2 import SingleTableView # type: ignore
from dispatch.models import Order, Trip, UploadFile
from dispatch.forms import OrderForm, FileUploadForm, OrderUpdateForm
from dispatch.tables import OrderTable, TripTable
from dispatch.models import Dispatch
from contrib.aws import s3_utils
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.contrib import messages
from dispatch.models.drivertruckassignment import DriverTruckAssignment
from subscriptions.models import QuotaService, UsageLog
from subscriptions.signals import check_quota_thresholds
from fleet.models import Customer
from django.contrib.contenttypes.models import ContentType
from ..utils import extract, map_order
from django.utils import timezone
from django.db.models import F
from dispatch.models import TripStatus, DispatchStatus, AssignmentStatus
from fleet.models import Driver, Truck, Carrier
from django.views.generic import View
from django.urls import reverse
from django.http import HttpResponseRedirect, FileResponse, HttpResponse
from django.views.decorators.clickjacking import xframe_options_exempt
from django.utils.decorators import method_decorator
import tempfile
import mimetypes

logger = logging.getLogger("django")


class OrderListView(LoginRequiredMixin, SingleTableView):
    model = Order
    table_class = OrderTable
    template_name = "order/list.html"
    paginate_by = 10

    def get_queryset(self):
        # Update the ordering field name here too
        return Order.objects.filter(tenant=self.request.user.profile.tenant).order_by(
            "-created_at"
        )

    def get_table(self, **kwargs):
        table = super().get_table(**kwargs)
        table.attrs = {
            "class": "table table-bordered table-striped table-hover clickable-table",
            "thead": {"class": "thead-light"},
        }
        return table


class OrderCreateView(LoginRequiredMixin, CreateView):
    model = Order
    form_class = OrderForm
    template_name = "order/create.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['tenant'] = self.request.user.profile.tenant
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["upload_form"] = FileUploadForm()
        context["cancel_url"] = reverse_lazy("dispatch:order_list")
        return context

    def form_valid(self, form):
        try:
            with transaction.atomic():
                # Set tenant and default values
                order = form.save(commit=False)
                order.tenant = self.request.user.profile.tenant
                
                # Save the order
                response = super().form_valid(form)
                
                messages.success(self.request, f"Order {order.order_number} created successfully.")
                return response
                
        except Exception as e:
            logger.error(f"Error creating order: {str(e)}")
            messages.error(self.request, f"Error creating order: {str(e)}")
            return self.form_invalid(form)

    def form_invalid(self, form):
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(self.request, f"{field}: {error}")
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse_lazy("dispatch:order_detail", kwargs={"pk": self.object.pk})

    def calculate_file_size_mb(self, file) -> float:
        """Calculate file size in megabytes with precision for small files"""
        try:
            return round(file.size / (1024 * 1024), 3)
        except Exception as e:
            logger.error(f"Error calculating file size: {str(e)}", exc_info=True)
            raise ValidationError(f"Error calculating file size: {str(e)}")

    def handle_uploaded_file(self, file, user):
        """Handle file upload with quota checking"""
        try:
            # Calculate file size
            file_size_mb = self.calculate_file_size_mb(file)
            logger.info(f"Upload file size: {file_size_mb}MB")

            # Check quotas before processing
            tenant = user.profile.tenant
            quota_service = QuotaService(tenant)

            # Check storage quota
            current_storage = quota_service.usage_period.storage_used_mb
            storage_limit = quota_service.get_limit("storage_limit_mb")
            if current_storage + file_size_mb > storage_limit:
                messages.error(
                    self.request,
                    f"Storage quota would be exceeded. Current: {current_storage:.2f}MB, Limit: {storage_limit}MB",
                )
                raise ValidationError("Storage quota exceeded")

            # Check order processing quota
            current_orders = quota_service.usage_period.orders_processed
            order_limit = quota_service.get_limit("monthly_order_limit")
            if current_orders >= order_limit:
                messages.error(
                    self.request,
                    f"Monthly order limit reached. Current: {current_orders}, Limit: {order_limit}",
                )
                raise ValidationError("Order limit exceeded")

            # Generate filename and paths
            filename = f"{secrets.token_urlsafe(6)}_{file.name}"
            file_dir = os.path.join(
                settings.MEDIA_ROOT,
                settings.ENV,
                "order_files",
                str(user.profile.tenant.id),
            )
            filepath = os.path.join(file_dir, filename)
            print(f"filepath_view: {filepath}")

            # Create directory if it doesn't exist
            os.makedirs(file_dir, exist_ok=True)

            # Write file
            with open(filepath, "wb+") as destination:
                for chunk in file.chunks():
                    destination.write(chunk)

            # Check thresholds and create warnings if needed
            check_quota_thresholds(tenant, quota_service.usage_period, self.request)

            return filepath, filename, file.content_type, file_dir

        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error handling file upload: {str(e)}", exc_info=True)
            messages.error(self.request, "Error processing file upload")
            raise ValidationError(f"Error processing file: {str(e)}")

    def post(self, request, *args, **kwargs):
        if "files" in request.FILES:
            try:
                form = FileUploadForm(request.POST, request.FILES)
                if not form.is_valid():
                    messages.error(request, "Invalid form submission")
                    return redirect("dispatch:order_create")

                files = request.FILES.getlist("files")
                if not files:
                    messages.error(request, "No files were selected")
                    return redirect("dispatch:order_create")

                file = files[0]
                tenant = request.user.profile.tenant

                # Handle file upload with quota checking
                filepath, filename, content_type, file_dir = self.handle_uploaded_file(
                    file, request.user
                )

                # Create upload file record
                uploaded_file = UploadFile.objects.create(
                    file=file,
                    tenant=tenant,
                    uploaded_by=request.user,
                )
                logger.info(f"Created UploadFile record: {uploaded_file.id}")

                # Upload to S3
                s3_key = f"{settings.ENV}/{tenant.id}/orders/{filename}"
                logger.info(f"s3_key: {s3_key}")
                s3_upload_success = s3_utils.upload_file(
                    filepath,
                    s3_key,
                )
                logger.info(f"s3_upload_success: {s3_upload_success}")

                if not s3_upload_success:
                    messages.error(request, "Failed to upload file to S3")
                    raise ValidationError("Failed to upload file to S3")

                try:
                    # Process the PDF file synchronously
                    logger.info(f"Starting PDF processing for file: {filename}")
                    
                    # Create tmp directory if it doesn't exist
                    tmp_dir = os.path.join(settings.BASE_DIR, "tmp", "documents")
                    os.makedirs(tmp_dir, exist_ok=True)
                    
                    # Download from S3 to process
                    local_path = os.path.join(tmp_dir, f"{secrets.token_urlsafe(6)}_{filename}")
                    logger.info(f"Downloading file from S3: {s3_key}")
                    s3_download_success = s3_utils.download_file(s3_key, local_path)
                    logger.info(f"s3_download_success: {s3_download_success}")
                    
                    if not s3_download_success:
                        raise Exception(f"Failed to download file from S3: {s3_key}")

                    # Get quota service for the tenant
                    quota_service = QuotaService(tenant)

                    # Calculate file size for quota
                    file_size_mb = round(os.path.getsize(local_path) / (1024 * 1024), 3)
                    logger.info(f"Processing file of size: {file_size_mb}MB")

                    # Extract data from the file
                    logger.info("Starting PDF extraction")
                    order_details, token_usage, pages = extract(local_path)
                    total_tokens = token_usage.get("total_tokens", 0)
                    logger.info(f"Extraction completed with {total_tokens} tokens used")

                    # Create order and trips
                    logger.info("Creating order and trips from extracted data")
                    order = map_order(order_details, tenant, s3_key)
                    
                    if not order:
                        raise ValidationError("Failed to create order")

                    # Calculate total storage including extracted text
                    total_storage_mb = file_size_mb + round(
                        len(pages.encode("utf-8")) / (1024 * 1024), 3
                    )

                    # Create usage log
                    UsageLog.objects.create(
                        tenant=tenant,
                        usage_period=quota_service.usage_period,
                        feature="order_processing",
                        tokens_used=total_tokens,
                        storage_delta_mb=total_storage_mb,
                        content_type=ContentType.objects.get_for_model(Order),
                        object_id=order.id,
                    )

                    # Update usage period totals
                    quota_service.usage_period.orders_processed += 1
                    quota_service.usage_period.tokens_used += total_tokens
                    quota_service.usage_period.storage_used_mb += total_storage_mb
                    quota_service.usage_period.save()

                    logger.info(
                        f"Successfully processed order {order.id}. "
                        f"File size: {file_size_mb}MB, Text size: {round(len(pages.encode('utf-8')) / (1024 * 1024), 3)}MB, "
                        f"Total storage: {total_storage_mb}MB, Tokens: {total_tokens}"
                    )

                    messages.success(request, "File uploaded and processed successfully.")

                    # Cleanup temporary files in a separate try block
                    try:
                        if os.path.exists(local_path):
                            os.remove(local_path)
                        if os.path.exists(filepath):
                            os.remove(filepath)
                    except Exception as e:
                        logger.warning(f"Failed to cleanup temporary files: {str(e)}")

                    return redirect("dispatch:order_detail", pk=order.id)

                except Exception as e:
                    # Clean up files in case of error
                    try:
                        if os.path.exists(local_path):
                            os.remove(local_path)
                        if os.path.exists(filepath):
                            os.remove(filepath)
                    except Exception as cleanup_error:
                        logger.warning(f"Failed to cleanup files after error: {str(cleanup_error)}")
                    
                    logger.error(f"Error processing PDF: {str(e)}", exc_info=True)
                    messages.error(request, f"Failed to process PDF: {str(e)}")
                    return redirect("dispatch:order_create", pk=order.id)

            except ValidationError as e:
                messages.error(request, str(e))
                return redirect("dispatch:order_create")
            except Exception as e:
                logger.error(f"Error processing upload: {str(e)}", exc_info=True)
                messages.error(request, "An unexpected error occurred")
                return redirect("dispatch:order_create")

        # Handle regular form submission
        return super().post(request, *args, **kwargs)


class OrderDetailView(LoginRequiredMixin, DetailView):
    model = Order
    template_name = "order/detail.html"
    context_object_name = "order"

    def get_queryset(self):
        """Get orders with related data."""
        return Order.objects.filter(
            tenant=self.request.user.profile.tenant
        ).select_related(
            'customer',
            'tenant'
        ).prefetch_related(
            'trips',
            'trips__status_history',
            'dispatches',
            'dispatches__driver',
            'dispatches__truck',
            'dispatches__carrier',
            'dispatches__status_history'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object

        # Get trips for this order with optimized queries
        trips = Trip.objects.filter(
            order=order
        ).prefetch_related(
            'status_history'
        ).order_by('-created_at')

        # Create table instance with trips
        table = TripTable(trips)
        context["table"] = table

        # Get dispatches with related data
        dispatches = Dispatch.objects.filter(
            order=order
        ).select_related(
            'driver',
            'truck',
            'carrier'
        ).prefetch_related(
            'status_history'
        ).order_by('-created_at')
        context["dispatches"] = dispatches

        # Add PDF URL to context if available - use local endpoint instead of presigned URL
        if order.pdf:
            logger.info(f"💫 Order Detail - PDF field value: {order.pdf}")
            # Use local URL instead of presigned URL to avoid JavaScript issues
            from django.urls import reverse
            context["pdf_url"] = reverse('dispatch:order_pdf', kwargs={'pk': order.pk})
            context["has_pdf"] = True
            logger.info(f"💫 Order Detail - Using local PDF URL: {context['pdf_url']}")
        else:
            logger.warning("💫 Order Detail - No PDF field value found")
            context["pdf_url"] = None
            context["has_pdf"] = False

        # Calculate order completion metrics
        total_trips = trips.count()
        completed_trips = trips.filter(status=TripStatus.COMPLETED).count()
        cancelled_trips = trips.filter(status=TripStatus.CANCELLED).count()
        in_progress_trips = trips.filter(status=TripStatus.IN_PROGRESS).count()

        context.update({
            'total_trips': total_trips,
            'completed_trips': completed_trips,
            'cancelled_trips': cancelled_trips,
            'in_progress_trips': in_progress_trips,
            'completion_percentage': (completed_trips / total_trips * 100) if total_trips > 0 else 0
        })

        # Check if all required trip data is complete
        trips_with_issues = trips.filter(
            Q(estimated_distance__isnull=True) |
            Q(estimated_duration__isnull=True) |
            Q(freight_value__isnull=True)
        )
        
        if trips_with_issues.exists():
            logger.info("Incomplete trips found:")
            for trip in trips_with_issues:
                issues = []
                if trip.estimated_distance is None:
                    issues.append("missing estimated distance")
                if trip.estimated_duration is None:
                    issues.append("missing estimated duration")
                if trip.freight_value is None:
                    issues.append("missing freight value")
                logger.info(f"Trip {trip.trip_id}: {', '.join(issues)}")

        context["trips_complete"] = (
            trips.exists() and  # At least one trip exists
            not trips_with_issues.exists()  # No trips have missing required data
        )

        # Add financial summary
        total_freight_value = sum(
            trip.freight_value or 0 
            for trip in trips
        )
        total_commission = sum(
            dispatch.commission_amount or 0 
            for dispatch in dispatches
        )

        context.update({
            'total_freight_value': total_freight_value,
            'total_commission': total_commission,
            'net_revenue': total_freight_value - total_commission
        })

        # Add related entities summary
        context.update({
            'unique_carriers': Carrier.objects.filter(
                dispatch__order=order
            ).distinct().count()
        })

        return context

    def post(self, request, *args, **kwargs):
        """Handle POST requests for order status updates."""
        order = self.get_object()
        action = request.POST.get('action')

        try:
            if action == 'cancel_order':
                self.cancel_order(order)
            elif action == 'complete_order':
                self.complete_order(order)
            elif action == 'reactivate_order':
                self.reactivate_order(order)
            else:
                messages.error(request, "Invalid action specified")
                return redirect('dispatch:order_detail', pk=order.pk)

            return redirect('dispatch:order_detail', pk=order.pk)

        except ValidationError as e:
            messages.error(request, str(e))
            return redirect('dispatch:order_detail', pk=order.pk)
        except Exception as e:
            logger.error(f"Error processing order action: {str(e)}")
            messages.error(request, f"Error processing action: {str(e)}")
            return redirect('dispatch:order_detail', pk=order.pk)

    def cancel_order(self, order):
        """Cancel the order and related entities."""
        if order.status == 'CANCELLED':
            raise ValidationError("Order is already cancelled")

        with transaction.atomic():
            # Cancel all active trips
            Trip.objects.filter(
                order=order,
                status__in=[TripStatus.PENDING, TripStatus.IN_PROGRESS]
            ).update(status=TripStatus.CANCELLED)

            # Cancel all active dispatches
            Dispatch.objects.filter(
                order=order,
                status__in=[
                    DispatchStatus.PENDING,
                    DispatchStatus.ASSIGNED,
                    DispatchStatus.IN_TRANSIT
                ]
            ).update(status=DispatchStatus.CANCELLED)

            # Cancel all active assignments
            active_assignments = DriverTruckAssignment.objects.filter(
                dispatch__order=order,
                status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY]
            )
            
            # Update each assignment individually to handle date validation
            current_time = timezone.now()
            for assignment in active_assignments:
                assignment.status = AssignmentStatus.CANCELLED
                # Ensure end_date is not before start_date
                if assignment.start_date and current_time < assignment.start_date:
                    # If assignment hasn't started yet, set end_date to start_date
                    assignment.end_date = assignment.start_date
                    logger.warning(
                        f"Assignment {assignment.id} end_date set to start_date ({assignment.start_date}) "
                        f"because current time ({current_time}) is before start_date during order cancellation (bulk)"
                    )
                else:
                    assignment.end_date = current_time
                assignment.save()

            # Update order status
            order.status = 'CANCELLED'
            order.save()

            messages.success(self.request, "Order cancelled successfully")

    def complete_order(self, order):
        """Complete the order if all requirements are met."""
        if order.status == 'COMPLETED':
            raise ValidationError("Order is already completed")

        # Check if all trips are complete
        incomplete_trips = Trip.objects.filter(
            order=order
        ).exclude(status=TripStatus.COMPLETED)

        if incomplete_trips.exists():
            raise ValidationError("Cannot complete order with incomplete trips")

        with transaction.atomic():
            # Complete any remaining dispatches
            Dispatch.objects.filter(
                order=order,
                status__in=[
                    DispatchStatus.ASSIGNED,
                    DispatchStatus.IN_TRANSIT
                ]
            ).update(status=DispatchStatus.COMPLETED)

            # Update order status
            order.status = 'COMPLETED'
            order.completed_at = timezone.now()
            order.save()

            messages.success(self.request, "Order completed successfully")

    def reactivate_order(self, order):
        """Reactivate a cancelled order."""
        if order.status != 'CANCELLED':
            raise ValidationError("Can only reactivate cancelled orders")

        with transaction.atomic():
            # Reactivate order
            order.status = 'PENDING'
            order.save()

            messages.success(self.request, "Order reactivated successfully")


class OrderEditView(LoginRequiredMixin, UpdateView):
    model = Order
    template_name = "order/edit.html"
    form_class = OrderUpdateForm

    def get_queryset(self):
        return Order.objects.filter(tenant=self.request.user.profile.tenant)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['tenant'] = self.request.user.profile.tenant
        return kwargs

    def get_dispatch_status(self):
        """Helper method to get dispatch status"""
        order = self.get_object()
        try:
            # Get the most recent active dispatch
            dispatch = order.dispatches.filter(is_active=True).first()
            return dispatch.status if dispatch else "Pending"
        except Exception:
            return "Pending"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["upload_form"] = FileUploadForm()
        context["cancel_url"] = reverse_lazy("dispatch:order_list")
        
        # Add PDF URL to context if available - use local endpoint like detail view
        if self.object.pdf:
            logger.info(f"💫 Order Edit - PDF field value: {self.object.pdf}")
            # Use local URL instead of presigned URL to avoid JavaScript issues
            from django.urls import reverse
            context["pdf_url"] = reverse('dispatch:order_pdf', kwargs={'pk': self.object.pk})
            context["has_pdf"] = True
            logger.info(f"💫 Order Edit - Using local PDF URL: {context['pdf_url']}")
        else:
            logger.warning("💫 Order Edit - No PDF field value found")
            context["pdf_url"] = None
            context["has_pdf"] = False
            
        dispatch_status = self.get_dispatch_status()
        context["is_editable"] = dispatch_status == "Pending"
        context["dispatch_status"] = dispatch_status
        return context

    def post(self, request, *args, **kwargs):
        """Override post to add additional logging and error handling"""
        self.object = self.get_object()
        
        # Log the POST data
        logger.info(f"POST data received: {request.POST}")
        
        form = self.get_form()
        if form.is_valid():
            try:
                return self.form_valid(form)
            except Exception as e:
                logger.error(f"Error in form_valid: {str(e)}", exc_info=True)
                messages.error(request, f"Error updating order: {str(e)}")
                return self.form_invalid(form)
        else:
            logger.error(f"Form validation failed: {form.errors}")
            return self.form_invalid(form)

    def form_valid(self, form):
        try:
            with transaction.atomic():
                # Set tenant and default values
                order = form.save(commit=False)
                order.tenant = self.request.user.profile.tenant
                
                # Save the order
                response = super().form_valid(form)
                
                messages.success(self.request, f"Order {order.order_number} created successfully.")
                return response
                
        except Exception as e:
            logger.error(f"Error creating order: {str(e)}")
            messages.error(self.request, f"Error creating order: {str(e)}")
            return self.form_invalid(form)

    def form_invalid(self, form):
        """Handle form validation failures"""
        logger.error("Form validation failed")
        logger.error(f"Form errors: {form.errors}")
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(self.request, f"{field}: {error}")
        return super().form_invalid(form)

    def dispatch(self, request, *args, **kwargs):
        try:
            dispatch_status = self.get_dispatch_status()
            if dispatch_status != "Pending" and request.method in ["POST", "PUT", "PATCH"]:
                raise PermissionDenied(
                    "This order cannot be edited as it is no longer in Pending status."
                )
            return super().dispatch(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error in dispatch: {str(e)}", exc_info=True)
            messages.error(request, str(e))
            return redirect("dispatch:order_list")

    def get_success_url(self):
        updated_fields = self.request.session.get('updated_fields', [])
        if updated_fields:
            message = f"Order updated successfully. Updated: {', '.join(updated_fields)}."
        else:
            message = "Order updated successfully."
        messages.success(self.request, message)
        # Clean up session
        if 'updated_fields' in self.request.session:
            del self.request.session['updated_fields']
        return reverse_lazy("dispatch:order_detail", kwargs={"pk": self.object.pk})


class OrderDeleteView(LoginRequiredMixin, DeleteView):
    model = Order
    template_name = 'order/confirm_delete.html'
    success_url = reverse_lazy('dispatch:order_list')

    def get_queryset(self):
        return Order.objects.filter(tenant=self.request.user.profile.tenant)

    def delete(self, request, *args, **kwargs):
        order = self.get_object()
        
        try:
            with transaction.atomic():
                # Store order number for success message
                order_number = order.order_number
                
                # Soft delete all related dispatches first
                dispatches = order.dispatches.all()
                for dispatch in dispatches:
                    # Cancel any active assignments
                    assignments = dispatch.assignments.filter(
                        status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY]
                    )
                    for assignment in assignments:
                        assignment.status = AssignmentStatus.CANCELLED
                        # Ensure end_date is not before start_date
                        current_time = timezone.now()
                        if assignment.start_date and current_time < assignment.start_date:
                            # If assignment hasn't started yet, set end_date to start_date
                            assignment.end_date = assignment.start_date
                            logger.warning(
                                f"Assignment {assignment.id} end_date set to start_date ({assignment.start_date}) "
                                f"because current time ({current_time}) is before start_date during order cancellation"
                            )
                        else:
                            assignment.end_date = current_time
                        assignment.deleted_at = timezone.now()
                        assignment.save()
                    
                    # Soft delete dispatch
                    dispatch.is_active = False
                    dispatch.deleted_at = timezone.now()
                    dispatch.save()
                
                # Soft delete all related trips
                trips = order.trips.all()
                for trip in trips:
                    trip.is_active = False
                    trip.deleted_at = timezone.now()
                    trip.save()
                
                # Soft delete all related files
                files = order.files.all()
                for file in files:
                    file.is_active = False
                    file.deleted_at = timezone.now()
                    file.save()
                
                # Finally soft delete the order
                order.is_active = False
                order.deleted_at = timezone.now()
                order.status = 'CANCELLED'
                order.save()
                
                # Add success message
                messages.success(request, f'Order #{order_number} has been deleted successfully.')
                
                return HttpResponseRedirect(self.success_url)
            
        except Exception as e:
            logger.error(f"Error deleting order: {str(e)}")
            messages.error(request, f"Failed to delete order: {str(e)}")
            return HttpResponseRedirect(reverse('dispatch:order_detail', kwargs={'pk': order.pk}))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.get_object()
        
        # Add counts of related objects
        context.update({
            'dispatch_count': order.dispatches.count(),
            'trip_count': order.trips.count(),
            'file_count': order.files.count()
        })
        
        return context


class OrderFileUploadView(LoginRequiredMixin, View):
    """View for handling file uploads for orders."""

    def post(self, request, pk):
        try:
            order = get_object_or_404(Order, pk=pk, tenant=request.user.profile.tenant)
            form = FileUploadForm(request.POST, request.FILES)
            
            if not form.is_valid():
                messages.error(request, "Invalid form submission")
                return redirect("dispatch:order_detail", pk=pk)

            files = request.FILES.getlist("files")
            if not files:
                messages.error(request, "No files were selected")
                return redirect("dispatch:order_detail", pk=pk)

            file = files[0]
            tenant = request.user.profile.tenant

            # Calculate file size
            file_size_mb = round(file.size / (1024 * 1024), 3)
            logger.info(f"Upload file size: {file_size_mb}MB")

            # Generate filename and paths
            filename = f"{secrets.token_urlsafe(6)}_{file.name}"
            file_dir = os.path.join(
                settings.MEDIA_ROOT,
                settings.ENV,
                "order_files",
                str(tenant.id),
            )
            filepath = os.path.join(file_dir, filename)

            # Create directory if it doesn't exist
            os.makedirs(file_dir, exist_ok=True)

            # Write file
            with open(filepath, "wb+") as destination:
                for chunk in file.chunks():
                    destination.write(chunk)

            # Create upload file record
            uploaded_file = UploadFile.objects.create(
                file=file,
                tenant=tenant,
                uploaded_by=request.user,
                order=order
            )
            logger.info(f"Created UploadFile record: {uploaded_file.id}")

            # Upload to S3
            s3_key = f"{settings.ENV}/{tenant.id}/orders/{filename}"
            logger.info(f"s3_key: {s3_key}")
            s3_upload_success = s3_utils.upload_file(
                filepath,
                s3_key,
            )
            logger.info(f"s3_upload_success: {s3_upload_success}")

            if not s3_upload_success:
                messages.error(request, "Failed to upload file to S3")
                raise ValidationError("Failed to upload file to S3")

            # Cleanup temporary file
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception as e:
                logger.warning(f"Failed to cleanup temporary file: {str(e)}")

            messages.success(request, "File uploaded successfully")
            return redirect("dispatch:order_detail", pk=pk)

        except ValidationError as e:
            messages.error(request, str(e))
            return redirect("dispatch:order_detail", pk=pk)
        except Exception as e:
            logger.error(f"Error processing upload: {str(e)}", exc_info=True)
            messages.error(request, "An unexpected error occurred")
            return redirect("dispatch:order_detail", pk=pk)


class OrderFileDownloadView(LoginRequiredMixin, View):
    """View for downloading order files."""

    def get(self, request, pk):
        try:
            order = get_object_or_404(Order, pk=pk, tenant=request.user.profile.tenant)
            uploaded_file = order.files.first()
            
            if not uploaded_file:
                messages.error(request, "No file found for this order")
                return redirect("dispatch:order_detail", pk=pk)

            # Generate presigned URL for S3 download
            s3_url = s3_utils.generate_presigned_url(uploaded_file.file)
            if not s3_url:
                messages.error(request, "Failed to generate download URL")
                return redirect("dispatch:order_detail", pk=pk)

            return HttpResponseRedirect(s3_url)

        except Exception as e:
            logger.error(f"Error downloading file: {str(e)}", exc_info=True)
            messages.error(request, "An unexpected error occurred")
            return redirect("dispatch:order_detail", pk=pk)


@method_decorator(xframe_options_exempt, name='dispatch')
class OrderPDFView(LoginRequiredMixin, View):
    """View for serving PDF files locally by downloading from S3."""

    def get(self, request, pk):
        try:
            logger.info(f"PDF request for order {pk} from user {request.user}")
            
            # Get the order
            order = get_object_or_404(
                Order.objects.select_related('tenant'),
                pk=pk, 
                tenant=request.user.profile.tenant
            )
            
            if not order.pdf:
                logger.warning(f"No PDF found for order {order.pk}")
                return HttpResponse("PDF not found", status=404)

            logger.info(f"Serving PDF for order {order.pk}, S3 key: {order.pdf}")
            
            # Create a temporary file to download the PDF
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                    temp_path = temp_file.name
                    
                    logger.info(f"Created temporary file: {temp_path}")
                    
                    # Download PDF from S3 to temporary file
                    logger.info(f"Attempting to download from S3: {order.pdf}")
                    success = s3_utils.download_file(order.pdf, temp_path)
                    
                    if not success:
                        logger.error(f"Failed to download PDF from S3: {order.pdf}")
                        return HttpResponse("Failed to retrieve PDF from storage", status=500)
                    
                    # Verify file exists and has content
                    if not os.path.exists(temp_path):
                        logger.error(f"Downloaded PDF file does not exist: {temp_path}")
                        return HttpResponse("Downloaded file not found", status=500)
                        
                    file_size = os.path.getsize(temp_path)
                    if file_size == 0:
                        logger.error(f"Downloaded PDF file is empty: {temp_path}")
                        return HttpResponse("Downloaded file is empty", status=500)
                    
                    logger.info(f"Successfully downloaded PDF to {temp_path}, size: {file_size} bytes")
                    
                    # Determine content type
                    content_type, _ = mimetypes.guess_type(temp_path)
                    if not content_type:
                        content_type = 'application/pdf'
                    
                    # Create response with the PDF file
                    try:
                        # Open file and create response
                        file_handle = open(temp_path, 'rb')
                        response = FileResponse(
                            file_handle,
                            content_type=content_type,
                            filename=f"order_{order.order_number}.pdf"
                        )
                        
                        # Set headers for inline display (not download)
                        response['Content-Disposition'] = f'inline; filename="order_{order.order_number}.pdf"'
                        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                        response['Pragma'] = 'no-cache'
                        response['Expires'] = '0'
                        
                        # Clean up temp file after response is sent
                        # Note: FileResponse will close the file handle automatically
                        # We need to clean up the temp file separately
                        def cleanup_temp_file():
                            try:
                                if os.path.exists(temp_path):
                                    os.unlink(temp_path)
                                    logger.info(f"Cleaned up temporary file: {temp_path}")
                            except Exception as e:
                                logger.warning(f"Failed to clean up temp file {temp_path}: {e}")
                        
                        # Schedule cleanup (this is a simple approach, could be improved)
                        import threading
                        threading.Timer(10.0, cleanup_temp_file).start()
                        
                        logger.info(f"Successfully serving PDF for order {order.pk}")
                        return response
                        
                    except Exception as e:
                        logger.error(f"Error creating PDF response: {str(e)}", exc_info=True)
                        # Clean up temp file on error
                        if os.path.exists(temp_path):
                            os.unlink(temp_path)
                        return HttpResponse(f"Error serving PDF: {str(e)}", status=500)
                        
            except Exception as e:
                logger.error(f"Error handling temporary file: {str(e)}", exc_info=True)
                return HttpResponse(f"Error processing PDF: {str(e)}", status=500)

        except Order.DoesNotExist:
            logger.warning(f"Order {pk} not found for user {request.user}")
            return HttpResponse("Order not found", status=404)
        except Exception as e:
            logger.error(f"Unexpected error serving PDF for order {pk}: {str(e)}", exc_info=True)
            return HttpResponse(f"Internal server error: {str(e)}", status=500)
