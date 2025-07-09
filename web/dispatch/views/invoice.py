"""Views for handling dispatch invoices."""

from django.views.generic import DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from dispatch.models import Dispatch

class DispatchInvoiceView(LoginRequiredMixin, DetailView):
    """View for generating dispatch invoices."""
    
    model = Dispatch
    template_name = "dispatch/invoice.html"
    context_object_name = "dispatch"

    def get_queryset(self):
        return Dispatch.objects.filter(tenant=self.request.user.profile.tenant)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dispatch = self.get_object()
        
        # Add order context
        context["order"] = dispatch.order
        
        # Add trips context
        context["trips"] = dispatch.order.trips.all()
        
        # Add total amount
        total_amount = sum(trip.amount for trip in context["trips"] if trip.amount)
        context["total_amount"] = total_amount
        
        return context 