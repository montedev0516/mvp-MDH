import logging
import pandas as pd
import pytz
import uuid
from django.conf import settings
from datetime import datetime, timedelta
from django.views.generic import (
    View,
    ListView,
    UpdateView,
    DeleteView,
    DetailView,
)
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import redirect
from django.http import HttpResponse, JsonResponse
from django.db.models import Q, Sum
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from expense.models import BVD, AccountPayableStatus
from fleet.models import Truck
from expense.forms import BVDForm
from expense.utils import BVDFileProcessor
from django.core.cache import cache
from django.utils import timezone
import csv

logger = logging.getLogger("django")


class BVDBaseView(LoginRequiredMixin):
    """Base view for BVD operations with common functionality"""
    model = BVD
    
    def get_queryset(self):
        """Get BVDs for current tenant"""
        # Log tenant info
        tenant = self.request.user.profile.tenant
        logger.info(f"Getting BVDs for tenant: {tenant.id} ({tenant.name})")
        
        # Get base queryset
        base_qs = BVD.objects.all()
        logger.info(f"Total BVDs (before tenant filter): {base_qs.count()}")
        
        # Log SQL query
        logger.info(f"SQL Query: {str(base_qs.query)}")
        
        # Apply tenant filter
        tenant_qs = base_qs.filter(tenant=tenant)
        logger.info(f"BVDs for tenant (before active filter): {tenant_qs.count()}")
        logger.info(f"Tenant filter SQL: {str(tenant_qs.query)}")
        
        # Apply active filter and select related
        final_qs = (
            tenant_qs.filter(is_active=True)
            .select_related("truck", "driver", "tenant")
            .order_by("-date")
        )
        logger.info(f"Final BVDs for tenant (active only): {final_qs.count()}")
        logger.info(f"Final SQL: {str(final_qs.query)}")
        
        # Log a few sample records
        sample_records = final_qs[:5]
        logger.info("Sample BVD records from base queryset:")
        for record in sample_records:
            logger.info(f"BVD: {record.id} | Unit: {record.unit} | Date: {record.date} | Amount: {record.amount} {record.currency}")
            logger.info(f"Record tenant: {record.tenant.id} | Active: {record.is_active}")
        
        return final_qs


class BVDListView(BVDBaseView, ListView):
    """List view for BVD records with search and filter capabilities"""
    template_name = "expense/fuel/bvd/list.html"
    context_object_name = "bvds"
    paginate_by = 50  # Add pagination

    def get_queryset(self):
        """Get BVDs with filters"""
        queryset = super().get_queryset()
        
        # Log initial queryset details
        logger.info(f"Initial BVD queryset count: {queryset.count()}")
        logger.info(f"Current tenant: {self.request.user.profile.tenant}")
        logger.info(f"Initial SQL: {str(queryset.query)}")
        
        # Log sample records
        sample_records = queryset[:5]
        logger.info("Sample records from initial queryset:")
        for record in sample_records:
            logger.info(f"BVD: {record.id} | Unit: {record.unit} | Date: {record.date} | Amount: {record.amount} {record.currency}")
            logger.info(f"Record tenant: {record.tenant.id} | Active: {record.is_active}")
        
        # Get search parameters
        search_query = self.request.GET.get("q")
        start_date = self.request.GET.get("start_date")
        end_date = self.request.GET.get("end_date")
        truck = self.request.GET.get("truck")
        card_number = self.request.GET.get("card_number")
        
        logger.info("Search parameters:")
        logger.info(f"Search query: {search_query}")
        logger.info(f"Start date: {start_date}")
        logger.info(f"End date: {end_date}")
        logger.info(f"Truck: {truck}")
        logger.info(f"Card number: {card_number}")
        
        # Apply filters
        if search_query:
            queryset = queryset.filter(
                Q(driver__first_name__icontains=search_query) |
                Q(driver__last_name__icontains=search_query) |
                Q(site_name__icontains=search_query) |
                Q(site_city__icontains=search_query) |
                Q(card_number__icontains=search_query)
            )
            logger.info(f"After search filter: {queryset.count()} records")
            logger.info(f"Search filter SQL: {str(queryset.query)}")
            
        if start_date:
            try:
                start_date = datetime.strptime(start_date, "%Y-%m-%d")
                if settings.USE_TZ:
                    start_date = timezone.make_aware(start_date)
                queryset = queryset.filter(date__gte=start_date)
                logger.info(f"After start date filter: {queryset.count()} records")
                logger.info(f"Start date filter SQL: {str(queryset.query)}")
            except ValueError:
                logger.warning(f"Invalid start date format: {start_date}")
                
        if end_date:
            try:
                end_date = datetime.strptime(end_date, "%Y-%m-%d")
                if settings.USE_TZ:
                    end_date = timezone.make_aware(end_date)
                # Add one day to include the entire end date
                end_date = end_date + timedelta(days=1)
                queryset = queryset.filter(date__lt=end_date)
                logger.info(f"After end date filter: {queryset.count()} records")
                logger.info(f"End date filter SQL: {str(queryset.query)}")
            except ValueError:
                logger.warning(f"Invalid end date format: {end_date}")
                
        if truck:
            queryset = queryset.filter(truck_id=truck)
            logger.info(f"After truck filter: {queryset.count()} records")
            logger.info(f"Truck filter SQL: {str(queryset.query)}")
            
        if card_number:
            queryset = queryset.filter(card_number__icontains=card_number)
            logger.info(f"After card number filter: {queryset.count()} records")
            logger.info(f"Card number filter SQL: {str(queryset.query)}")
            
        # Order by date descending
        queryset = queryset.order_by("-date")
        
        # Log final queryset details
        logger.info(f"Final queryset count: {queryset.count()}")
        logger.info(f"Final SQL: {str(queryset.query)}")
        
        # Log final sample records
        final_sample_records = queryset[:5]
        logger.info("Sample records from final queryset:")
        for record in final_sample_records:
            logger.info(f"BVD: {record.id} | Unit: {record.unit} | Date: {record.date} | Amount: {record.amount} {record.currency}")
            logger.info(f"Record tenant: {record.tenant.id} | Active: {record.is_active}")
            
        return queryset

    def get_context_data(self, **kwargs):
        """Add additional context for filters and summary statistics"""
        context = super().get_context_data(**kwargs)
        
        # Add form to context
        context['form'] = BVDForm(tenant=self.request.user.profile.tenant)
        
        # Log context data
        logger.info("Context data:")
        logger.info(f"Context keys: {context.keys()}")
        logger.info(f"BVDs in context: {context.get('bvds')}")
        logger.info(f"BVDs count: {context.get('bvds').count() if context.get('bvds') else 0}")
        
        # Get current filter values
        context["search_query"] = self.request.GET.get("q", "")
        context["start_date"] = self.request.GET.get("start_date", "")
        context["end_date"] = self.request.GET.get("end_date", "")
        context["selected_truck"] = self.request.GET.get("truck", "")
        context["card_number"] = self.request.GET.get("card_number", "")
        
        # Get all active trucks for filter dropdown
        context["trucks"] = Truck.objects.filter(
            tenant=self.request.user.profile.tenant,
            is_active=True
        ).order_by("unit")
        
        # Calculate summary statistics
        queryset = self.get_queryset()
        context["record_count"] = queryset.count()
        
        # Use aggregate to calculate totals with proper defaults
        totals = queryset.aggregate(
            total_quantity=Sum("quantity"),
            total_amount=Sum("amount")
        )
        
        context["total_quantity"] = totals["total_quantity"] or 0
        context["total_amount"] = totals["total_amount"] or 0
        
        # Calculate status counts
        context["pending_count"] = queryset.filter(status='Pending').count()
        context["accounted_count"] = queryset.filter(status='Accounted').count() 
        context["paid_count"] = queryset.filter(status='Paid').count()
        
        # Add filter preservation for pagination
        current_filters = {}
        for key, value in self.request.GET.items():
            if key != 'page' and value:
                current_filters[key] = value
        context['current_filters'] = current_filters
        
        # Log final context data
        logger.info("Final context data:")
        logger.info(f"Context keys: {context.keys()}")
        
        return context

    def post(self, request, *args, **kwargs):
        try:
            form = BVDForm(request.POST, tenant=request.user.profile.tenant)
            
            if form.is_valid():
                bvd = form.save(commit=False)
                bvd.tenant = request.user.profile.tenant
                bvd.save()
                messages.success(request, "Fuel expense created successfully!")
            else:
                messages.error(request, "Please check the form and correct any errors.")
                
        except Exception as e:
            logger.error(f"Error creating fuel expense: {str(e)}")
            messages.error(request, "Unable to create fuel expense. Please try again.")
                    
        return self.get(request, *args, **kwargs)


class BVDDetailView(BVDBaseView, DetailView):
    """Detail view for a BVD record"""
    template_name = "expense/fuel/bvd/detail.html"
    context_object_name = "bvd"


class BVDUpdateView(BVDBaseView, UpdateView):
    """Update view for a BVD record"""
    form_class = BVDForm
    template_name = "expense/fuel/bvd/update.html"
    success_url = reverse_lazy("fuel_expense_bvd_list")

    def get_form_kwargs(self):
        logger.info("Getting form kwargs")
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.user.profile.tenant
        logger.info(f"Form kwargs: {kwargs}")
        return kwargs

    def get_initial(self):
        logger.info("Getting initial data")
        initial = super().get_initial()
        logger.info(f"Initial data: {initial}")
        return initial

    def form_valid(self, form):
        logger.info("Form validation started")
        try:
            self.object = form.save(commit=False)
            self.object.tenant = self.request.user.profile.tenant
            self.object.save()
            messages.success(self.request, "Fuel expense updated successfully!")
            logger.info("Form saved successfully")
            return redirect(self.success_url)
        except ValidationError as e:
            logger.error(f"Validation error: {str(e)}")
            messages.error(self.request, "Unable to save the changes. Please check your data and try again.")
            return self.form_invalid(form)
        except Exception as e:
            logger.error(f"Unexpected error saving fuel expense: {str(e)}")
            messages.error(self.request, "An unexpected error occurred. Please try again.")
            return self.form_invalid(form)

    def form_invalid(self, form):
        logger.error("Form validation failed")
        logger.error(f"Form errors: {form.errors}")
        
        messages.error(self.request, "Please correct the highlighted errors and try again.")
        return super().form_invalid(form)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        logger.info(f"Retrieved object: date={obj.date}, tenant={obj.tenant}")
        return obj


class BVDDeleteView(BVDBaseView, DeleteView):
    """Delete view for a BVD record"""
    success_url = reverse_lazy("fuel_expense_bvd_list")

    def delete(self, request, *args, **kwargs):
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(request, "Fuel expense deleted successfully!")
            return response
        except Exception as e:
            logger.error(f"Error deleting fuel expense: {str(e)}")
            messages.error(request, "Unable to delete the fuel expense. Please try again.")
            return redirect("fuel_expense_bvd_list")


class BVDSearchView(BVDBaseView, ListView):
    """Search view for BVD records with filtering capabilities"""
    template_name = "expense/fuel/bvd/list.html"
    context_object_name = "bvds"

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Get search parameters
        search_query = self.request.GET.get("q")
        start_date = self.request.GET.get("start_date")
        end_date = self.request.GET.get("end_date")
        truck = self.request.GET.get("truck")
        card_number = self.request.GET.get("card_number")
        status = self.request.GET.get("status")

        # Apply filters
        if search_query:
            queryset = queryset.filter(
                Q(driver__first_name__icontains=search_query) |
                Q(driver__last_name__icontains=search_query) |
                Q(site_name__icontains=search_query) |
                Q(site_city__icontains=search_query) |
                Q(card_number__icontains=search_query)
            )

        if start_date:
            try:
                start_date = datetime.strptime(start_date, "%Y-%m-%d")
                queryset = queryset.filter(date__gte=start_date)
            except ValueError:
                logger.warning(f"Invalid start date format: {start_date}")

        if end_date:
            try:
                end_date = datetime.strptime(end_date, "%Y-%m-%d")
                end_date = end_date.replace(hour=23, minute=59, second=59)
                queryset = queryset.filter(date__lte=end_date)
            except ValueError:
                logger.warning(f"Invalid end date format: {end_date}")

        if truck:
            queryset = queryset.filter(truck_id=truck)

        if card_number:
            queryset = queryset.filter(card_number=card_number)
            
        if status:
            queryset = queryset.filter(status=status)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add search form context
        context.update({
            "search_query": self.request.GET.get("q", ""),
            "start_date": self.request.GET.get("start_date", ""),
            "end_date": self.request.GET.get("end_date", ""),
            "selected_truck": self.request.GET.get("truck", ""),
            "card_number": self.request.GET.get("card_number", ""),
            "status": self.request.GET.get("status", ""),
        })

        # Add summary statistics
        queryset = self.get_queryset()
        context.update({
            "total_quantity": queryset.aggregate(Sum("quantity"))["quantity__sum"] or 0,
            "total_amount": queryset.aggregate(Sum("amount"))["amount__sum"] or 0,
            "record_count": queryset.count(),
        })

        return context


class BVDImportView(BVDBaseView, View):
    """Import BVD records from CSV or Excel file"""

    def post(self, request, *args, **kwargs):
        """Handle file upload and import"""
        try:
            # Ensure this is an AJAX request
            if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                logger.warning("BVD import accessed without AJAX - redirecting")
                messages.error(request, "Import must be done through the import modal.")
                return redirect('fuel_expense_bvd_list')
            
            # Validate user and tenant
            if not hasattr(request.user, 'profile') or not request.user.profile.tenant:
                return JsonResponse({
                    "status": "error",
                    "message": "User session invalid. Please log in again."
                })

            # Get uploaded file
            file_obj = request.FILES.get("bvd_file")
            if not file_obj:
                return JsonResponse({
                    "status": "error", 
                    "message": "No file selected. Please choose a file to upload."
                })

            # Validate file size (10MB limit)
            if file_obj.size > 10 * 1024 * 1024:
                return JsonResponse({
                    "status": "error", 
                    "message": "File is too large. Please upload a file smaller than 10MB."
                })

            # Validate file extension
            file_extension = file_obj.name.split(".")[-1].lower()
            if file_extension not in ["csv", "xlsx", "xls"]:
                return JsonResponse({
                    "status": "error",
                    "message": "Invalid file format. Please upload a CSV or Excel file (.csv, .xlsx, .xls)."
                })

            # Validate file content isn't empty
            if file_obj.size == 0:
                return JsonResponse({
                    "status": "error",
                    "message": "The uploaded file is empty. Please check your file and try again."
                })

            logger.info(f"🚀Starting BVD import - File: {file_obj.name}, Size: {file_obj.size} bytes, AJAX: {request.headers.get('X-Requested-With')}")

            # Generate batch ID
            batch_id = str(uuid.uuid4())
            logger.info(f"Generated batch ID: {batch_id}")

            # Process file with comprehensive error handling
            try:
                processor = BVDFileProcessor(file_obj, request.user.profile.tenant.id, batch_id)
                result = processor.process_file()
                
                if not result:
                    return JsonResponse({
                        "status": "error",
                        "message": "File processing failed. Please check your file format and try again."
                    })

            except UnicodeDecodeError:
                logger.error("File encoding error during BVD import")
                return JsonResponse({
                    "status": "error",
                    "message": "File encoding error. Please save your file as UTF-8 and try again."
                })
            except pd.errors.EmptyDataError:
                logger.error("Empty CSV file during BVD import")
                return JsonResponse({
                    "status": "error",
                    "message": "The CSV file appears to be empty or has no data rows."
                })
            except pd.errors.ParserError as e:
                logger.error(f"CSV parsing error: {str(e)}")
                return JsonResponse({
                    "status": "error",
                    "message": "Unable to read the file. Please check the file format and try again."
                })
            except FileNotFoundError:
                logger.error("File not found during BVD import")
                return JsonResponse({
                    "status": "error",
                    "message": "File upload failed. Please try uploading again."
                })
            except PermissionError:
                logger.error("Permission error during BVD import")
                return JsonResponse({
                    "status": "error",
                    "message": "File access denied. Please try again."
                })
            except MemoryError:
                logger.error("Memory error during BVD import - file too large")
                return JsonResponse({
                    "status": "error",
                    "message": "File is too large to process. Please split into smaller files."
                })
            except Exception as e:
                logger.error(f"Unexpected error during file processing: {str(e)}")
                return JsonResponse({
                    "status": "error",
                    "message": "An unexpected error occurred while processing the file. Please try again."
                })

            # Log result
            logger.info(f"✅ BVD import completed - Batch: {batch_id}, Success: {result['success']}, Errors: {result['errors']}, Skipped: {result.get('skipped', 0)}")

            # Prepare user-friendly response
            total_processed = result.get("processed", result["total"])
            success_count = result["success"]
            error_count = result["errors"] 
            skipped_count = result.get("skipped", 0)
            
            # Determine status based on results
            if success_count == 0 and error_count == 0 and skipped_count > 0:
                status = "completed_with_skips"
            elif error_count > 0:
                status = "completed_with_errors"
            elif skipped_count > 0:
                status = "completed_with_skips"
            else:
                status = "success"

            response_data = {
                "status": status,
                "total": result["total"],
                "processed": total_processed,
                "success": success_count,
                "errors": error_count,
                "skipped": skipped_count,
                "error_details": result["error_details"][-5:] if result["error_details"] else [],
                "skipped_details": result.get("skipped_details", [])[-5:],
                "skipped_units": result.get("skipped_units", {})
            }

            # Create user-friendly message
            if success_count == 0 and error_count == 0 and skipped_count == 0:
                response_data["message"] = "No records were processed. Please check your file format and data."
            elif success_count == 0 and skipped_count > 0:
                response_data["message"] = (
                    f"No records imported. {skipped_count} records were skipped (missing trucks, no assignments, etc.). "
                    f"Please check your data and truck assignments."
                )
            elif error_count > 0 and skipped_count > 0:
                response_data["message"] = (
                    f"Import completed: {success_count} records imported successfully. "
                    f"{error_count} records had errors, {skipped_count} records were skipped."
                )
            elif error_count > 0:
                response_data["message"] = (
                    f"Import completed: {success_count} records imported successfully. "
                    f"{error_count} records had errors."
                )
            elif skipped_count > 0:
                response_data["message"] = (
                    f"Import completed: {success_count} records imported successfully. "
                    f"{skipped_count} records were skipped (missing trucks, no assignments, etc.)."
                )
            else:
                response_data["message"] = f"Successfully imported {success_count} records."

            return JsonResponse(response_data)

        except KeyError as e:
            logger.error(f"Missing required data during BVD import: {str(e)}")
            return JsonResponse({
                "status": "error",
                "message": "Invalid request data. Please try again."
            })
        except ValueError as e:
            logger.error(f"Invalid data format during BVD import: {str(e)}")
            return JsonResponse({
                "status": "error",
                "message": "Invalid data format in the request. Please check your input."
            })
        except Exception as e:
            logger.error(f"Unexpected error in BVD import view: {str(e)}")
            return JsonResponse({
                "status": "error",
                "message": "An unexpected error occurred. Please try again or contact support."
            })

    def get(self, request, *args, **kwargs):
        """Check import progress"""
        batch_id = request.GET.get('batch_id')
        if not batch_id:
            return JsonResponse({"error": "No batch ID provided"}, status=400)

        status = cache.get(f"bvd_import_{batch_id}_status")
        if not status:
            return JsonResponse({"error": "Import status not found"}, status=404)

        return JsonResponse(status)


class BVDExportView(BVDBaseView, View):
    """Export BVD records to CSV"""

    def get(self, request, *args, **kwargs):
        """Export BVD records to CSV"""
        try:
            # Get filtered queryset
            queryset = self.get_queryset()
            
            # Log export request
            logger.info(f"Exporting BVD records - Count: {queryset.count()}")

            # Create response with CSV writer
            response = HttpResponse(content_type="text/csv")
            response["Content-Disposition"] = 'attachment; filename="bvd_export.csv"'
            writer = csv.writer(response)

            # Write header row
            writer.writerow([
                "Date",
                "Time",
                "Company Name",
                "Card Number",
                "Driver Name",
                "Unit #",
                "Site Number",
                "Site Name",
                "Site City",
                "Province/State",
                "Quantity",
                "UOM",
                "Retail PPU",
                "Billed PPU",
                "Pre-tax Amount",
                "PST",
                "GST",
                "HST",
                "QST",
                "Discount",
                "Final Amount",
                "Currency",
                "Odometer",
                "Auth Code",
                "Status"
            ])

            # Write data rows
            for bvd in queryset:
                writer.writerow([
                    bvd.date.strftime("%Y-%m-%d"),
                    bvd.date.strftime("%H:%M"),
                    bvd.company_name,
                    bvd.card_number,
                    bvd.driver.get_full_name() if bvd.driver else "-",
                    bvd.unit,
                    bvd.site_number,
                    bvd.site_name,
                    bvd.site_city,
                    bvd.prov_st,
                    f"{bvd.quantity:.2f}",
                    bvd.uom,
                    f"{bvd.retail_ppu:.4f}",
                    f"{bvd.billed_ppu:.4f}",
                    f"{bvd.pre_tax_amt:.2f}",
                    f"{bvd.pst:.2f}",
                    f"{bvd.gst:.2f}",
                    f"{bvd.hst:.2f}",
                    f"{bvd.qst:.2f}",
                    f"{bvd.discount:.2f}",
                    f"{bvd.amount:.2f}",
                    bvd.currency,
                    bvd.odometer,
                    bvd.auth_code,
                    bvd.status
                ])

            # Log successful export
            logger.info("BVD export completed successfully")
            return response

        except Exception as e:
            logger.error(f"Error exporting BVD records: {str(e)}")
            messages.error(request, f"Error exporting records: {str(e)}")
            return redirect("fuel_expense_bvd_list")
