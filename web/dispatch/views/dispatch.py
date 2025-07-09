import logging
import json
from collections import Counter
from django.template.loader import render_to_string
from django.template import TemplateDoesNotExist
from django.utils import timezone
from django.db import transaction, models
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import DetailView, CreateView, DeleteView
from django.core.exceptions import ValidationError
from django_tables2 import SingleTableView
from django.views.generic.edit import UpdateView
from django import forms
from django.core.serializers.json import DjangoJSONEncoder
from models.models import Currency
from weasyprint import HTML, CSS
from django.db.models import Sum
from dispatch.models import (
    Order,
    Dispatch,
    Trip,
    DispatchStatus,
    TripStatus,
    DriverTruckAssignment,
    AssignmentStatus,
    StatusHistory,
)
from fleet.models import Customer, Driver, Truck, Carrier
from contrib.aws import s3_utils
from ..forms import DispatchForm, DispatchDetailForm
from ..tables import DispatchTable

logger = logging.getLogger("django")


class DispatchCreateView(LoginRequiredMixin, CreateView):
    model = Dispatch
    form_class = DispatchForm
    template_name = "dispatch/create.html"
    context_object_name = "dispatch"

    def dispatch(self, request, *args, **kwargs):
        # Get the order first to ensure it exists
        self.order = get_object_or_404(
            Order.objects.select_related("tenant"),
            pk=self.kwargs.get("order_pk"),
            tenant=self.request.user.profile.tenant,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.user.profile.tenant

        # Add order_id to form initial data
        order_pk = self.kwargs.get("order_pk")
        if order_pk:
            kwargs["initial"] = kwargs.get("initial", {})
            kwargs["initial"].update({
                "order_id": order_pk,
                "order_number": self.order.order_number,
                "order_date": self.order.created_at,
                "status": DispatchStatus.PENDING
            })
        
        if not kwargs.get("instance"):
            initial_data = self.get_initial_data()
            # Remove form-only fields from initial_data before creating instance
            instance_data = {k: v for k, v in initial_data.items() 
                           if k not in ['order_number', 'order_date']}
            kwargs["instance"] = Dispatch(
                tenant=self.request.user.profile.tenant,
                order=self.order,
                **instance_data,
            )

        return kwargs

    def get_initial_data(self):
        """Helper method to get initial data"""
        # Get customer from order's customer information
        customer = None
        if self.order.customer_name:
            customer = Customer.objects.filter(
                name__iexact=self.order.customer_name,
                tenant=self.request.user.profile.tenant
            ).first()

            if not customer:
                # Create new customer
                customer = Customer.objects.create(
                    name=self.order.customer_name,
                    address=self.order.customer_address or '',
                    email=self.order.customer_email or '',
                    phone=self.order.customer_phone or '',
                    tenant=self.request.user.profile.tenant
                )

        # Get trip from order
        trips = Trip.objects.filter(
            order=self.order,
            tenant=self.request.user.profile.tenant
        ).order_by('-created_at')
        trip = trips.first()

        # Default commission amount
        commission_amount = 0.0
        if self.order.load_total:
            # Default 10% commission
            commission_amount = float(self.order.load_total) * 0.1

        # Add error handling for Counter
        currencies = trips.values_list("currency", flat=True)
        commission_currency = Currency.CAD  # Default value
        if currencies:
            currency_counts = Counter(currencies)
            if currency_counts:
                commission_currency = currency_counts.most_common(1)[0][0]

        initial_data = {
            "order_number": self.order.order_number,
            "order_date": self.order.created_at,
            "customer": customer,
            "trip": trip,
            "commission_amount": commission_amount,
            "commission_percentage": 12.0,  # Default value
            "commission_currency": commission_currency,
            "status": DispatchStatus.PENDING,
        }
        return initial_data

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order_pk = self.kwargs.get("order_pk")
        
        if order_pk:
            try:
                order = Order.objects.get(
                    pk=order_pk,
                    tenant=self.request.user.profile.tenant
                )
                context["order"] = order
                context["load_total"] = order.load_total
            except Order.DoesNotExist:
                pass
        
        # Get trips data
        trips = Trip.objects.filter(
            order=self.order
        )
        
        # Serialize trips data for JavaScript
        trips_data = []
        for trip in trips:
            trips_data.append({
                'id': str(trip.id),  # Convert UUID to string
                'freight_value': float(trip.freight_value) if trip.freight_value else 0,
                'currency': trip.currency or 'CAD',
                'pickup_date': trip.order.pickup_date.isoformat() if trip.order.pickup_date else None,
                'delivery_date': trip.order.delivery_date.isoformat() if trip.order.delivery_date else None,
                'estimated_duration': str(trip.estimated_duration) if trip.estimated_duration else None,
            })

        # Add PDF URL to context if available - use local endpoint like other views
        if self.order.pdf:
            logger.info(f"💫 Dispatch Create - PDF field value: {self.order.pdf}")
            # Use local URL instead of presigned URL to avoid JavaScript issues
            from django.urls import reverse
            context["pdf_url"] = reverse('dispatch:order_pdf', kwargs={'pk': self.order.pk})
            context["has_pdf"] = True
            logger.info(f"💫 Dispatch Create - Using local PDF URL: {context['pdf_url']}")
        else:
            logger.warning("💫 Dispatch Create - No PDF field value found")
            context["pdf_url"] = None
            context["has_pdf"] = False

        # Add data to context
        context.update({
            'order': self.order,
            'load_total': self.order.load_total,
            'trips': json.dumps(trips_data, cls=DjangoJSONEncoder),
            'total_commission': Dispatch.objects.filter(order=self.order).aggregate(
                total=Sum('commission_amount')
            )['total'] or 0,
        })

        return context

    def form_invalid(self, form):
        """Handle form validation errors"""
        logger.error("Form validation failed")
        for field, errors in form.errors.items():
            logger.error(f"Field {field} errors: {errors}")
            for error in errors:
                messages.error(self.request, f"{field}: {error}")

        for error in form.non_field_errors():
            messages.error(self.request, error)

        return super().form_invalid(form)

    def form_valid(self, form):
        """Handle valid form submission"""
        try:
            with transaction.atomic():
                # Set tenant and save dispatch
                form.instance.tenant = self.request.user.profile.tenant
                dispatch = form.save(commit=False)

                # Handle commission calculation
                commission_percentage = form.cleaned_data.get("commission_percentage")
                if commission_percentage is not None:
                    load_total = float(self.order.load_total) if self.order.load_total else 0
                    if load_total > 0:
                        dispatch.commission_amount = round(load_total * (float(commission_percentage) / 100), 2)

                # Save the dispatch
                dispatch.save()
                self.object = dispatch

                # Create a status history entry for dispatch creation
                StatusHistory.log_status_change(
                    obj=dispatch,
                    old_status='',
                    new_status=dispatch.status,
                    user=self.request.user,
                    metadata={
                        'dispatch_id': dispatch.dispatch_id,
                        'order_number': dispatch.order_number,
                        'customer': str(dispatch.customer) if dispatch.customer else None,
                    }
                )

                # Synchronize related statuses
                dispatch.sync_related_statuses(user=self.request.user)

                # Mark order as processed
                self.order.processed = True
                self.order.save()

                messages.success(self.request, "Dispatch created successfully!")
                return HttpResponseRedirect(self.get_success_url())

        except ValidationError as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)
        except Exception as e:
            logger.error(f"Error creating dispatch: {str(e)}", exc_info=True)
            messages.error(self.request, f"Error creating dispatch: {str(e)}")
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse_lazy("dispatch:dispatch_detail", kwargs={"pk": self.object.pk})

    def clean(self):
        cleaned_data = super().clean()
        logger.debug("Cleaning form data:", cleaned_data)  # Debug print

        # Prevent manual setting of INVOICED status
        if cleaned_data.get("status") == DispatchStatus.INVOICED:
            raise ValidationError("Cannot manually set status to Invoiced")

        return cleaned_data

    def post(self, request, *args, **kwargs):
        logger.debug(f"POST data: {request.POST}")

        # Check for customer and trip values
        logger.debug(f"Customer ID in POST: {request.POST.get('customer')}")
        logger.debug(f"Trip ID in POST: {request.POST.get('trip')}")

        return super().post(request, *args, **kwargs)


class DispatchListView(LoginRequiredMixin, SingleTableView):
    model = Dispatch
    table_class = DispatchTable
    template_name = "dispatch/list.html"
    paginate_by = 10

    def get_queryset(self):
        """Optimized queryset with proper relationships loaded"""
        return Dispatch.objects.filter(
            tenant=self.request.user.profile.tenant
        ).select_related(
            'order',
            'order__customer', 
            'trip',
            'trip__order',
            'customer',
            'driver',
            'driver__driveremployment',
            'truck',
            'truck__carrier',
            'carrier',
            'tenant'
        ).prefetch_related(
            'assignments',
            'assignments__driver',
            'assignments__truck',
            'status_history',
            'notifications'
        ).order_by("-created_at")

    def get_table(self, **kwargs):
        table = super().get_table(**kwargs)
        table.attrs = {
            "class": "table table-bordered table-striped table-hover clickable-table",
            "thead": {"class": "thead-light"},
        }
        return table


class DispatchDetailView(UserPassesTestMixin, DetailView):
    template_name = "dispatch/detail.html"
    model = Dispatch
    context_object_name = "dispatch"

    def test_func(self):
        return self.request.user.is_authenticated

    def get_queryset(self):
        """Get queryset filtered by tenant."""
        return Dispatch.objects.filter(
            tenant=self.request.user.profile.tenant
        ).select_related("order", "trip", "customer")

    def get_context_data(self, **kwargs):
        """Add additional context for rendering the template."""
        context = super().get_context_data(**kwargs)
        dispatch = self.get_object()

        # Add form to context in read-only mode
        context["form"] = DispatchDetailForm(instance=dispatch, is_readonly=True, tenant=self.request.user.profile.tenant)

        # Add PDF URL to context if available
        if dispatch.order and dispatch.order.pdf:
            logger.info(f"💫 Dispatch Detail - Order PDF field value: {dispatch.order.pdf}")
            pdf_url = s3_utils.generate_presigned_url(dispatch.order.pdf)
            if pdf_url:
                logger.info(f"💫 Dispatch Detail - Generated presigned URL: {pdf_url}")
                context["pdf_url"] = pdf_url
            else:
                logger.warning("💫 Dispatch Detail - Failed to generate presigned URL")
                messages.warning(self.request, "Failed to load the order document. Please try refreshing the page.")
        else:
            logger.warning("💫 Dispatch Detail - No PDF field value found")

        # Get status history
        status_history = dispatch.status_history.all().order_by("-created_at")
        context["status_history"] = status_history

        # Add order information
        if dispatch.order:
            context["order"] = dispatch.order
            context["trips"] = dispatch.order.trips.all()

        # Get the trip details if there's a linked trip
        if dispatch.trip:
            context["trip"] = dispatch.trip

        # Add status history
        context["logs"] = StatusHistory.objects.filter(
            content_type__model='dispatch',
            object_id=dispatch.id
        ).order_by("-created_at")[:10]

        # Check if dispatch is in a final state
        context["is_final"] = dispatch.status in [
            DispatchStatus.INVOICED,
            DispatchStatus.PAYMENT_RECEIVED,
            DispatchStatus.CANCELLED,
        ]

        # Add URL names to context for template use
        context["dispatch_list_url"] = reverse_lazy("dispatch:dispatch_list")
        context["dispatch_detail_url"] = reverse_lazy("dispatch:dispatch_detail", kwargs={"pk": dispatch.pk})
        context["dispatch_update_url"] = reverse_lazy("dispatch:dispatch_update", kwargs={"pk": dispatch.pk})
        context["dispatch_delete_url"] = reverse_lazy("dispatch:dispatch_delete", kwargs={"pk": dispatch.pk})

        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Block modifications for final statuses
        if self.object.status in [DispatchStatus.CANCELLED, DispatchStatus.INVOICED]:
            messages.error(
                request, "Cannot modify dispatch once it is Cancelled or Invoiced."
            )
            return redirect("dispatch:dispatch_detail", pk=self.object.pk)

        # Handle invoice generation
        if "generate_invoice" in request.POST:
            if self.object.status != DispatchStatus.ASSIGNED:
                messages.error(
                    request,
                    "Can only generate invoice for dispatches with Assigned status.",
                )
                return redirect("dispatch:dispatch_detail", pk=self.object.pk)

            order = get_object_or_404(
                Order,
                pk=self.object.order.id,
                tenant=self.request.user.profile.tenant,
            )
            # Update all trips associated with this order to INVOICED status
            Trip.objects.filter(order=order).update(status=TripStatus.INVOICED)
            return self.generate_invoice(request, self.object)

        # Handle form submission
        form = DispatchDetailForm(request.POST, instance=self.object, tenant=self.request.user.profile.tenant)

        if form.is_valid():
            try:
                with transaction.atomic():
                    dispatch = form.save(commit=False)
                    old_status = self.object.status
                    new_status = form.cleaned_data.get("status", old_status)

                    # Calculate commission amount based on percentage
                    if form.cleaned_data.get("commission_percentage") is not None:
                        load_total = float(dispatch.order.load_total) if dispatch.order.load_total else 0
                        if load_total > 0:
                            dispatch.commission_amount = load_total * (float(form.cleaned_data["commission_percentage"]) / 100)

                    # Save the dispatch
                    dispatch.save()

                    # If status changed, update related trips
                    if old_status != new_status:
                        # Create a status history entry for dispatch status change
                        StatusHistory.log_status_change(
                            obj=dispatch,
                            old_status=old_status,
                            new_status=new_status,
                            user=self.request.user,
                            metadata={
                                'dispatch_id': dispatch.dispatch_id,
                                'order_number': dispatch.order_number,
                                'customer': str(dispatch.customer) if dispatch.customer else None,
                            }
                        )

                        # Update trip status based on dispatch status
                        if dispatch.trip:
                            trip = dispatch.trip
                            if new_status == DispatchStatus.ASSIGNED:
                                trip.status = TripStatus.IN_PROGRESS
                            elif new_status == DispatchStatus.DELIVERED:
                                trip.status = TripStatus.COMPLETED
                            elif new_status == DispatchStatus.CANCELLED:
                                trip.status = TripStatus.CANCELLED
                            trip.save()

                messages.success(request, "Dispatch updated successfully!")
                return redirect("dispatch:dispatch_detail", pk=dispatch.pk)

            except Exception as e:
                messages.error(request, f"Error updating dispatch: {str(e)}")
                return self.render_to_response(self.get_context_data(form=form))

        context = self.get_context_data(form=form)
        return self.render_to_response(context)

    def generate_invoice(self, request, dispatch: Dispatch):
        """
        Generate an invoice PDF for a dispatch and change its status to Invoiced.
        """
        # Validate dispatch status
        if dispatch.status != DispatchStatus.ASSIGNED:
            messages.error(
                request,
                "Can only generate invoice for dispatches with Assigned status.",
            )
            return redirect("dispatch:dispatch_detail", pk=dispatch.pk)

        try:
            # Generate unique invoice number
            invoice_number = dispatch.dispatch_id

            # Get the associated trip
            trip = dispatch.order.trip_set.first()

            # Get organization details
            organization = organization.objects.filter(
                tenant=request.user.profile.tenant
            ).first()

            if not organization:
                messages.error(
                    request,
                    "Organization details not found. Please set up your organization first.",
                )
                return redirect("dispatch:dispatch_detail", pk=dispatch.pk)

            # Get the order's currency
            order_currency = (
                dispatch.order.load_currency or "USD"
            )  # Default to USD if not set

            # Prepare context with dynamic currency
            context = {
                "dispatch": dispatch,
                "invoice_number": invoice_number,
                "date": timezone.now(),
                "company": organization,
                "load_total": {
                    "amount": dispatch.order.load_total,
                    "currency": order_currency,
                },
                "trip": trip,
                "billing_info": {
                    "commission_amount": dispatch.commission_amount,
                    "commission_percentage": dispatch.commission_percentage,
                    "commission_currency": dispatch.commission_currency
                    or order_currency,
                },
                "customer": dispatch.customer,
                "order": {
                    "number": dispatch.order_number,
                    "date": dispatch.order_date,
                    "currency": order_currency,
                },
            }

            # Render invoice HTML template
            try:
                html_string = render_to_string(
                    "dispatch/invoice_template.html", context
                )
            except TemplateDoesNotExist:
                messages.error(request, "Invoice template not found.")
                return redirect("dispatch:dispatch_detail", pk=dispatch.pk)

            # Convert to PDF using WeasyPrint
            try:
                html = HTML(string=html_string, base_url=request.build_absolute_uri())

                # Create response with PDF content
                response = HttpResponse(content_type="application/pdf")
                response["Content-Disposition"] = (
                    f'attachment; filename="invoice_{invoice_number}.pdf"'
                )

                # Generate PDF with custom styling
                css = CSS(
                    string="""
                    @page {
                        size: letter;
                        margin: 1.5cm;
                        @bottom-right {
                            content: "Page " counter(page) " of " counter(pages);
                        }
                    }
                    body { font-family: Arial, sans-serif; }
                    .invoice-header { margin-bottom: 20px; }
                    .company-details { margin-bottom: 30px; }
                    .billing-details { margin-bottom: 20px; }
                    .invoice-table { width: 100%; border-collapse: collapse; }
                    .invoice-table th, .invoice-table td {
                        border: 1px solid #ddd;
                        padding: 8px;
                    }
                    .invoice-total { margin-top: 20px; text-align: right; }
                """
                )

                html.write_pdf(response, stylesheets=[css])

                # Update dispatch status to Invoiced
                dispatch.status = DispatchStatus.INVOICED
                dispatch.save()

                # Store invoice generation metadata
                dispatch.invoice_number = invoice_number
                dispatch.invoice_date = timezone.now()
                dispatch.invoice_generated_by = request.user
                dispatch.save()

                messages.success(
                    request, f"Invoice {invoice_number} generated successfully."
                )
                return response

            except Exception as e:
                messages.error(request, f"Error generating PDF: {str(e)}")
                return redirect("dispatch:dispatch_detail", pk=dispatch.pk)

        except Exception as e:
            messages.error(request, f"Error generating invoice: {str(e)}")
            return redirect("dispatch:dispatch_detail", pk=dispatch.pk)


class DispatchUpdateView(LoginRequiredMixin, UpdateView):
    template_name = "dispatch/update.html"
    form_class = DispatchDetailForm
    model = Dispatch

    def get_queryset(self):
        """Get the base queryset with all necessary related fields."""
        return (
            Dispatch.objects.filter(tenant=self.request.user.profile.tenant)
            .select_related(
                "order",
                "trip",
                "customer",
                "tenant"
            )
        )

    def get_form_kwargs(self):
        """Add tenant and additional data to form kwargs."""
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.user.profile.tenant
        
        # Get the dispatch instance
        dispatch = self.get_object()
        
        # Add initial data for trip if not set
        if not kwargs.get("initial"):
            kwargs["initial"] = {}
        
        if dispatch.trip:
            kwargs["initial"]["trip"] = dispatch.trip.id

        return kwargs

    def get_context_data(self, **kwargs):
        """Add additional context for rendering the template."""
        context = super().get_context_data(**kwargs)
        dispatch = self.get_object()

        # Add PDF URL to context if available
        if dispatch.order and dispatch.order.pdf:
            logger.info(f"💫 Dispatch Update - Order PDF field value: {dispatch.order.pdf}")
            pdf_url = s3_utils.generate_presigned_url(dispatch.order.pdf)
            if pdf_url:
                logger.info(f"💫 Dispatch Update - Generated presigned URL: {pdf_url}")
                context["pdf_url"] = pdf_url
            else:
                logger.warning("💫 Dispatch Update - Failed to generate presigned URL")
                messages.warning(self.request, "Failed to load the order document. Please try refreshing the page.")
        else:
            logger.warning("💫 Dispatch Update - No PDF field value found")

        # Get status history
        status_history = dispatch.status_history.all().order_by("-created_at")
        context["status_history"] = status_history

        # Add order information
        if dispatch.order:
            context["order"] = dispatch.order
            context["trips"] = dispatch.order.trips.all()

        return context

    def get_form(self, form_class=None):
        """Make fields readonly if dispatch is in final state."""
        form = super().get_form(form_class)
        dispatch = self.get_object()

        # Fields to always make readonly in update view
        readonly_fields = []

        # If dispatch status is final, make most fields readonly
        if dispatch.status in [
            DispatchStatus.INVOICED,
            DispatchStatus.PAYMENT_RECEIVED,
            DispatchStatus.CANCELLED,
        ]:
            readonly_fields.extend([
                "customer", "trip",
                "commission_amount", "commission_currency", "commission_percentage",
                "order_number", "order_date"
            ])

            # Only display status change field if not in final state
            if dispatch.status in [DispatchStatus.INVOICED, DispatchStatus.PAYMENT_RECEIVED]:
                form.fields["status"].choices = [
                    (dispatch.status, dict(DispatchStatus.choices)[dispatch.status])
                ]
                readonly_fields.append("status")

        # Set readonly fields without disabling them
        for field_name in readonly_fields:
            if field_name in form.fields:
                if isinstance(form.fields[field_name].widget, forms.Select):
                    # For select fields, we need to keep them enabled to show the value
                    form.fields[field_name].widget.attrs['readonly'] = True
                    form.fields[field_name].widget.attrs['style'] = 'pointer-events: none; background-color: #e9ecef;'
                else:
                    # For other fields, we can use readonly
                    form.fields[field_name].widget.attrs['readonly'] = True

        # Update trip choices if needed
        if 'trip' in form.fields:
            trips = Trip.objects.filter(
                order=dispatch.order,
                tenant=self.request.user.profile.tenant
            )
            form.fields['trip'].queryset = trips

        return form

    def form_invalid(self, form):
        """Log form errors when form is invalid"""
        logger.error("Form validation failed")
        for field, errors in form.errors.items():
            logger.error(f"Field {field} errors: {errors}")
            for error in errors:
                messages.error(self.request, f"{field}: {error}")

        for error in form.non_field_errors():
            messages.error(self.request, error)

        return super().form_invalid(form)

    def form_valid(self, form):
        """Handle valid form data and save the model instance."""
        logger.info("Form validation successful, attempting to save...")
        try:
            with transaction.atomic():
                dispatch = form.instance
                old_status = Dispatch.objects.get(pk=dispatch.pk).status
                new_status = form.cleaned_data.get("status")

                logger.info(f"Old status: {old_status}, New status: {new_status}")

                # Validate status transition
                try:
                    dispatch.validate_status_transition(new_status)
                except ValidationError as e:
                    messages.error(self.request, str(e))
                    return self.form_invalid(form)

                # Save the form first to update the instance
                self.object = form.save()
                logger.info("Form saved successfully")

                # If status changed, create a status history entry and synchronize statuses
                if old_status != new_status:
                    logger.info(f"Status changed from {old_status} to {new_status}")
                    
                    # Create a status history entry for dispatch status change
                    StatusHistory.log_status_change(
                        obj=dispatch,
                        old_status=old_status,
                        new_status=new_status,
                        user=self.request.user,
                        metadata={
                            'dispatch_id': dispatch.dispatch_id,
                            'order_number': dispatch.order_number,
                            'customer': str(dispatch.customer) if dispatch.customer else None,
                        }
                    )

                    # Handle status synchronization
                    try:
                        dispatch.sync_related_statuses(old_status=old_status, user=self.request.user)
                    except ValidationError as e:
                        # Rollback to old status
                        dispatch.status = old_status
                        dispatch.save()
                        messages.error(self.request, f"Status synchronization failed: {str(e)}")
                        return self.form_invalid(form)
                    except Exception as e:
                        logger.error(f"Error synchronizing statuses: {str(e)}")
                        dispatch.status = old_status
                        dispatch.save()
                        messages.error(self.request, f"Error synchronizing statuses: {str(e)}")
                        return self.form_invalid(form)

                    # Create notifications for status change
                    try:
                        from dispatch.models import Notification
                        priority = dispatch.get_status_priority(new_status)
                        Notification.create_status_change_notification(
                            obj=dispatch,
                            old_status=old_status,
                            new_status=new_status,
                            priority=priority
                        )
                    except Exception as e:
                        logger.error(f"Error creating notification: {str(e)}")
                        # Don't rollback the status change just for notification failure
                        messages.warning(self.request, "Status updated but notification creation failed")

                messages.success(self.request, "Dispatch updated successfully!")
                return HttpResponseRedirect(self.get_success_url())

        except Exception as e:
            logger.error(f"Error updating dispatch: {str(e)}")
            messages.error(self.request, f"Error updating dispatch: {str(e)}")
            return self.form_invalid(form)

    def get_success_url(self):
        """URL to redirect to after successful form submission."""
        try:
            return reverse_lazy("dispatch:dispatch_detail", kwargs={"pk": self.object.pk})
        except Exception as e:
            logger.error(f"Error generating success URL: {str(e)}")
            return reverse_lazy("dispatch:dispatch_list")


class DispatchDeleteView(LoginRequiredMixin, DeleteView):
    model = Dispatch
    template_name = "dispatch/delete.html"

    def get_queryset(self):
        return Dispatch.objects.filter(tenant=self.request.user.profile.tenant)

    def delete(self, request, *args, **kwargs):
        """Handle deletion with proper error handling and messaging."""
        try:
            self.object = self.get_object()
            
            # Check if dispatch can be deleted
            if self.object.status in [DispatchStatus.INVOICED, DispatchStatus.PAYMENT_RECEIVED]:
                messages.error(
                    self.request,
                    f"Cannot delete dispatch {self.object.dispatch_id} because it has been invoiced or payment has been received."
                )
                return HttpResponseRedirect(reverse_lazy("dispatch:dispatch_detail", kwargs={"pk": self.object.pk}))
            
            # Store dispatch info for success message
            dispatch_id = self.object.dispatch_id
            order_number = self.object.order.order_number if self.object.order else "N/A"
            
            # Perform deletion
            with transaction.atomic():
                # Log the deletion
                logger.info(f"Deleting dispatch {dispatch_id} for order {order_number} by user {request.user.username}")
                
                # Create a final status history entry for deletion
                StatusHistory.log_status_change(
                    obj=self.object,
                    old_status=self.object.status,
                    new_status='DELETED',
                    user=self.request.user,
                    metadata={
                        'dispatch_id': dispatch_id,
                        'order_number': order_number,
                        'deletion_reason': 'Manual deletion by user',
                    }
                )
                
                # Delete the object
                self.object.delete()
                
                messages.success(
                    self.request,
                    f"Dispatch {dispatch_id} (Order: {order_number}) has been successfully deleted."
                )
                
                return HttpResponseRedirect(self.get_success_url())
                
        except Exception as e:
            logger.error(f"Error deleting dispatch: {str(e)}", exc_info=True)
            messages.error(
                self.request,
                f"Error deleting dispatch: {str(e)}"
            )
            return HttpResponseRedirect(reverse_lazy("dispatch:dispatch_detail", kwargs={"pk": self.object.pk}))

    def get_success_url(self):
        """Return the URL to redirect to after successful deletion."""
        return reverse_lazy("dispatch:dispatch_list")
