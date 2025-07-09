from django.shortcuts import get_object_or_404, redirect  # type: ignore
from django.views.generic import ListView, DetailView, DeleteView  # type: ignore
from django.contrib.auth.mixins import LoginRequiredMixin  # type: ignore
from dispatch.forms import TripForm  # type: ignore
from dispatch.models import (
    Order, Trip, TripStatus,
    DriverTruckAssignment, AssignmentStatus, StatusHistory
)  # type: ignore
from dispatch.models.log import TripLog  # type: ignore
from dispatch.models.dispatch import DispatchStatus  # type: ignore
from fleet.models import Driver, Truck  # type: ignore
from django.contrib import messages  # type: ignore
from django.db.models import Q  # type: ignore
from django.views import View  # type: ignore
from django.shortcuts import render  # type: ignore
from contrib.aws import s3_utils  # type: ignore
import logging
from django.utils import timezone  # type: ignore
from django.db import transaction  # Import transaction directly from django.db
from django.core.exceptions import ValidationError  # type: ignore
from django.urls import reverse_lazy  # type: ignore
from datetime import timedelta  # type: ignore

logger = logging.getLogger(__name__)


class TripListView(LoginRequiredMixin, ListView):
    model = Trip
    template_name = "trip/list.html"
    context_object_name = "trips"
    paginate_by = 20

    def get_queryset(self):
        """Get trips filtered by tenant and optionally by order."""
        order_id = self.kwargs.get("order_id")
        queryset = Trip.objects.filter(
            tenant=self.request.user.profile.tenant
        ).select_related("order")

        if order_id:
            queryset = queryset.filter(order_id=order_id)

        # Add search functionality
        search_query = self.request.GET.get("q")
        if search_query:
            queryset = queryset.filter(
                Q(order__order_number__icontains=search_query)
                | Q(order__customer_name__icontains=search_query)
                | Q(order__origin__icontains=search_query)
                | Q(order__destination__icontains=search_query)
            )

        return queryset.order_by("-created_at")

    def get_context_data(self, **kwargs):
        """Add additional context data."""
        context = super().get_context_data(**kwargs)

        # If filtered by order, add order to context
        order_id = self.kwargs.get("order_id")
        if order_id:
            try:
                context["order"] = Order.objects.get(
                    pk=order_id, tenant=self.request.user.profile.tenant
                )
            except Order.DoesNotExist:
                pass

        # Add search query to context if present
        search_query = self.request.GET.get("q")
        if search_query:
            context["search_query"] = search_query

        return context


class TripCreateView(LoginRequiredMixin, View):
    template_name = "trip/create.html"

    def get(self, request, *args, **kwargs):
        order_id = kwargs.get("order_id")
        try:
            order = Order.objects.get(
                pk=order_id, tenant=self.request.user.profile.tenant
            )
        except Order.DoesNotExist:
            return redirect("dispatch:order_list")

        # Check for existing trips for this order
        existing_trips = Trip.objects.filter(
            order=order, tenant=self.request.user.profile.tenant
        ).order_by("-created_at")

        form = TripForm(
            initial={
                "currency": "USD",  # Default currency
                "commission_percentage": 10.0,  # Default commission percentage
                "status": TripStatus.PENDING,  # Default status
            },
            tenant=self.request.user.profile.tenant,
            order=order
        )

        # Get PDF URL if available
        pdf_url = None
        if order.pdf:
            pdf_url = s3_utils.generate_presigned_url(order.pdf)

        context = {
            "form": form,
            "order": order,
            "existing_trips": existing_trips,
            "pdf_url": pdf_url,
        }
        return render(request, self.template_name, context)

    def get_form_kwargs(self):
        kwargs = {}
        if self.request.method in ("POST", "PUT"):
            kwargs.update(
                {
                    "data": self.request.POST,
                    "files": self.request.FILES,
                }
            )

        # Add order if available
        order_id = self.kwargs.get("order_id")
        if order_id:
            try:
                order = Order.objects.get(
                    pk=order_id, tenant=self.request.user.profile.tenant
                )
                kwargs["order"] = order
            except Order.DoesNotExist:
                pass
        return kwargs

    def get_form(self, form_class=None):
        kwargs = self.get_form_kwargs()

        # Make sure we add order to the form
        if "order" not in kwargs:
            order_id = self.kwargs.get("order_id")
            if order_id:
                try:
                    order = Order.objects.get(
                        pk=order_id, tenant=self.request.user.profile.tenant
                    )
                    kwargs["order"] = order
                except Order.DoesNotExist:
                    pass

        # Initialize the form with proper kwargs
        form = TripForm(**kwargs)
        return form

    def post(self, request, *args, **kwargs):
        try:
            order_id = self.kwargs.get("order_id")
            order = Order.objects.get(
                pk=order_id, tenant=self.request.user.profile.tenant
            )
        except Order.DoesNotExist:
            logger.error(f"Order not found with id {self.kwargs.get('order_id')}")
            messages.error(request, "Order not found")
            return redirect("dispatch:order_list")

        # Log the POST data
        logger.info(f"POST data: {request.POST}")

        # Create form
        form = TripForm(
            request.POST,
            tenant=self.request.user.profile.tenant,
            order=order
        )

        if form.is_valid():
            try:
                # Create Trip instance but don't save yet
                trip = form.save(commit=False)
                
                # Ensure status is set to PENDING for new trips
                if not trip.pk:
                    trip.status = TripStatus.PENDING
                
                trip.tenant = self.request.user.profile.tenant
                trip.created_by = request.user
                trip.order = order

                # Log the trip state before saving
                logger.info(f"💋Trip before save - status: {trip.status}")

                # Save with user for proper logging
                trip.save(user=request.user)
                logger.info(f"💋Trip created successfully with status {trip.status}")

                # Note: Order status should remain PENDING until dispatch is created
                # Trip creation alone doesn't indicate actual work has begun

                messages.success(request, "Trip created successfully.")
                return redirect("dispatch:order_detail", pk=order.pk)
            except Exception as e:
                logger.error(f"Error saving trip: {str(e)}", exc_info=True)
                messages.error(request, f"Error creating trip: {str(e)}")
        else:
            logger.error(f"Form validation failed: {form.errors}")
            messages.error(request, "Please correct the errors below")

        # Re-render the form with errors
        # Get PDF URL if available
        pdf_url = None
        if order.pdf:
            pdf_url = s3_utils.generate_presigned_url(order.pdf)

        # Get existing trips for this order
        existing_trips = Trip.objects.filter(
            order=order, tenant=self.request.user.profile.tenant
        ).order_by("-created_at")

        context = {
            "form": form,
            "order": order,
            "existing_trips": existing_trips,
            "pdf_url": pdf_url,
        }
        return render(request, self.template_name, context)


class TripUpdateView(LoginRequiredMixin, View):
    """View for updating trips."""
    template_name = "trip/edit.html"

    def get_trip(self, pk):
        """Get trip by pk with tenant filter."""
        return get_object_or_404(
            Trip.objects.select_related("order"),
            pk=pk,
            tenant=self.request.user.profile.tenant,
        )

    def get_context_data(self, **kwargs):
        """Add additional context data."""
        context = kwargs
        trip = self.get_trip(self.kwargs.get("pk"))
        context["trip"] = trip

        # Get PDF URL if available
        if trip.order and trip.order.pdf:
            logger.info(f"💫 Trip Update - Order PDF field value: {trip.order.pdf}")
            pdf_url = s3_utils.generate_presigned_url(trip.order.pdf)
            if pdf_url:
                logger.info(f"💫 Trip Update - Generated presigned URL: {pdf_url}")
                context["pdf_url"] = pdf_url
            else:
                logger.warning("💫 Trip Update - Failed to generate presigned URL")
                messages.warning(self.request, "Failed to load the order document. Please try refreshing the page.")

        return context

    def get(self, request, *args, **kwargs):
        """Handle GET request."""
        trip = self.get_trip(kwargs.get("pk"))
        if not trip:
            return redirect("dispatch:trip_list")

        # Extract hours and minutes from estimated_duration
        estimated_duration_hours = 0
        estimated_duration_minutes = 0
        if trip.estimated_duration:
            total_seconds = int(trip.estimated_duration.total_seconds())
            estimated_duration_hours = total_seconds // 3600
            estimated_duration_minutes = (total_seconds % 3600) // 60

        # Create form with initial duration values
        form = TripForm(
            instance=trip,
            tenant=self.request.user.profile.tenant,
            order=trip.order,
            initial={
                'estimated_duration_hours': estimated_duration_hours,
                'estimated_duration_minutes': estimated_duration_minutes,
            }
        )

        context = self.get_context_data(form=form)
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        """Handle POST request."""
        trip = self.get_trip(kwargs.get("pk"))
        logger.info(f"💫 Trip Update POST - Processing update for trip {trip.pk}")
        logger.info(f"💫 Trip Update POST - Form data: {request.POST}")

        # Check if trip is editable based on status
        is_editable = trip.status in [
            TripStatus.PENDING,
            TripStatus.IN_PROGRESS,
        ]

        if not is_editable:
            messages.error(request, "This trip cannot be edited in its current status.")
            return redirect("dispatch:trip_detail", pk=trip.pk)

        # Create form with trip instance and POST data
        form = TripForm(
            request.POST,
            instance=trip,
            tenant=self.request.user.profile.tenant,
            order=trip.order
        )

        if form.is_valid():
            logger.info("💫 Trip Update POST - Form is valid")
            try:
                with transaction.atomic():
                    # Track status changes for order updates
                    old_status = trip.status
                    new_status = form.cleaned_data.get("status")
                    logger.info(f"💫 Trip Update POST - Status change: {old_status} -> {new_status}")

                    # Save trip
                    trip = form.save(commit=False)
                    trip.modified_by = request.user
                    trip.tenant = self.request.user.profile.tenant

                    # Handle duration fields
                    hours = int(request.POST.get('estimated_duration_hours', 0) or 0)
                    minutes = int(request.POST.get('estimated_duration_minutes', 0) or 0)
                    trip.estimated_duration = timedelta(hours=hours, minutes=minutes)
                    
                    # Log the changes
                    logger.info(f"💫 Trip Update POST - Changes to save: {form.changed_data}")
                    logger.info(f"💫 Trip Update POST - New duration: {trip.estimated_duration}")
                    
                    # Save the trip
                    trip.save()
                    logger.info(f"💫 Trip Update POST - Trip saved successfully")

                    # Save many-to-many relationships if any
                    form.save_m2m()

                    # Create log entry for status change
                    if old_status != new_status:
                        # Get the display values for the statuses
                        old_status_display = dict(TripStatus.choices).get(
                            old_status, old_status
                        )
                        new_status_display = dict(TripStatus.choices).get(
                            new_status, new_status
                        )

                        trip.log_status_change(old_status_display, new_status_display, request.user)
                        logger.info(f"💫 Trip Update POST - Status change logged: {old_status_display} -> {new_status_display}")

                        # Update order status if needed
                        self.update_order_status_from_trip(trip)

                messages.success(request, "Trip updated successfully!")
                return redirect("dispatch:trip_detail", pk=trip.pk)

            except Exception as e:
                logger.error(f"💫 Trip Update POST - Error saving trip: {str(e)}", exc_info=True)
                messages.error(request, f"Error updating trip: {str(e)}")
                context = self.get_context_data(form=form)
                return render(request, self.template_name, context)
        else:
            logger.error(f"💫 Trip Update POST - Form validation failed: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")

        context = self.get_context_data(form=form)
        return render(request, self.template_name, context)

    def update_order_status_from_trip(self, trip):
        """Update order status based on trip status changes."""
        order = trip.order
        logger.info(f"💫 Trip Update - Updating order status for order {order.pk}")

        # Only update order status for completion or cancellation scenarios
        # Order should remain PENDING until dispatch is created/assigned
        
        # If all trips are complete, mark order as completed
        if trip.status == TripStatus.COMPLETED:
            all_trips_completed = True
            for t in order.trips.all():
                if t.status != TripStatus.COMPLETED:
                    all_trips_completed = False
                    break

            if all_trips_completed:
                logger.info(f"💫 Trip Update - All trips completed, marking order {order.pk} as COMPLETED")
                order.status = "COMPLETED"
                order.save(update_fields=["status"])

        # If trip is canceled, check if order should revert to PENDING
        elif trip.status == TripStatus.CANCELLED:
            active_trips = order.trips.exclude(
                status__in=[TripStatus.CANCELLED, TripStatus.COMPLETED]
            ).exists()

            if not active_trips:
                # Check if there are any completed trips
                completed_trips = order.trips.filter(
                    status=TripStatus.COMPLETED
                ).exists()

                if completed_trips:
                    # Some trips were completed, others canceled - order remains as is
                    logger.info(f"💫 Trip Update - Some trips completed, keeping order {order.pk} status unchanged")
                else:
                    # All trips were canceled - only revert to PENDING if no dispatches exist
                    active_dispatches = order.dispatches.exclude(
                        status__in=[DispatchStatus.CANCELLED, DispatchStatus.COMPLETED]
                    ).exists()
                    
                    if not active_dispatches:
                        logger.info(f"💫 Trip Update - All trips cancelled and no active dispatches, marking order {order.pk} as PENDING")
                        order.status = "PENDING"
                        order.save(update_fields=["status"])


class TripDetailView(LoginRequiredMixin, DetailView):
    """View for displaying trip details."""
    model = Trip
    template_name = "trip/detail.html"
    context_object_name = "trip"

    def get_context_data(self, **kwargs):
        """Add additional context data."""
        context = super().get_context_data(**kwargs)
        trip = self.get_object()

        # Add order information
        if trip.order:
            context["order"] = trip.order
            context["order_status"] = trip.order.get_status_display()

            # Add PDF URL if available
            if trip.order.pdf:
                logger.info(f"💫 Trip Detail - Order PDF field value: {trip.order.pdf}")
                pdf_url = s3_utils.generate_presigned_url(trip.order.pdf)
                if pdf_url:
                    logger.info(f"💫 Trip Detail - Generated presigned URL: {pdf_url}")
                    context["pdf_url"] = pdf_url
                else:
                    logger.warning("💫 Trip Detail - Failed to generate presigned URL")
                    messages.warning(self.request, "Failed to load the order document. Please try refreshing the page.")
            else:
                logger.warning("💫 Trip Detail - No PDF field value found")

        # Add financial information
        context["total_estimated_cost"] = (
            (trip.fuel_estimated or 0) +
            (trip.toll_estimated or 0)
        )
        context["total_actual_cost"] = (
            (trip.fuel_actual or 0) +
            (trip.toll_actual or 0)
        )

        # Add duration information
        if trip.estimated_duration:
            hours = trip.estimated_duration.total_seconds() // 3600
            minutes = (trip.estimated_duration.total_seconds() % 3600) // 60
            context["estimated_duration_hours"] = int(hours)
            context["estimated_duration_minutes"] = int(minutes)

        if trip.actual_duration:
            hours = trip.actual_duration.total_seconds() // 3600
            minutes = (trip.actual_duration.total_seconds() % 3600) // 60
            context["actual_duration_hours"] = int(hours)
            context["actual_duration_minutes"] = int(minutes)

        # Get trip logs - combine both StatusHistory and TripLog
        status_logs = StatusHistory.objects.filter(
            content_type__model='trip',
            object_id=trip.id,
            tenant=trip.tenant
        ).select_related('changed_by').order_by("-changed_at")
        
        trip_logs = TripLog.objects.filter(
            trip=trip,
            tenant=trip.tenant
        ).select_related('created_by').order_by("-created_at")
        
        # Combine and sort all logs by timestamp
        all_logs = []
        
        # Add status history logs
        for log in status_logs:
            all_logs.append({
                'type': 'status_change',
                'timestamp': log.changed_at,
                'user': log.changed_by,
                'old_status': log.old_status,
                'new_status': log.new_status,
                'notes': log.notes,
            })
        
        # Add trip logs
        for log in trip_logs:
            all_logs.append({
                'type': 'trip_log',
                'timestamp': log.created_at,
                'user': log.created_by,
                'action': log.action,
                'message': log.message,
            })
        
        # Sort by timestamp (newest first)
        all_logs.sort(key=lambda x: x['timestamp'], reverse=True)
        
        context["trip_logs"] = all_logs

        return context


class TripDeleteView(LoginRequiredMixin, DeleteView):
    """View for deleting trips."""
    
    model = Trip
    template_name = "trip/delete.html"
    context_object_name = "trip"
    
    def get_queryset(self):
        return Trip.objects.filter(tenant=self.request.user.profile.tenant)
    
    def get_success_url(self):
        messages.success(self.request, "Trip deleted successfully.")
        if self.object.order:
            return reverse_lazy("dispatch:order_detail", kwargs={"pk": self.object.order.pk})
        return reverse_lazy("dispatch:trip_list")
