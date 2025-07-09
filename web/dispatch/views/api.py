"""API views for the dispatch app."""

import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from dispatch.models import Order, Trip, UploadFile, DriverTruckAssignment, AssignmentStatus, TripStatus
from dispatch.forms import FileUploadForm
from contrib.aws import s3_utils
import os
import secrets
from django.conf import settings
from django.utils import timezone
from fleet.models import Driver, Truck
from datetime import datetime

logger = logging.getLogger(__name__)

@login_required
@require_http_methods(["POST"])
def order_extract(request):
    """Extract order information from uploaded file."""
    try:
        form = FileUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return JsonResponse({"error": "Invalid form submission"}, status=400)

        files = request.FILES.getlist("files")
        if not files:
            return JsonResponse({"error": "No files were selected"}, status=400)

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
            return JsonResponse({"error": "Failed to upload file to S3"}, status=500)

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

            # Create order
            logger.info("Creating order from extracted data")
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

            # Cleanup temporary files
            try:
                if os.path.exists(local_path):
                    os.remove(local_path)
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception as e:
                logger.warning(f"Failed to cleanup temporary files: {str(e)}")

            # Return success response with extracted data
            return JsonResponse({
                "message": "File processed successfully",
                "order_id": str(order.id),
                "extracted_data": {
                    "order_number": order.order_number,
                    "customer_name": order.customer_name,
                    "customer_email": order.customer_email,
                    "customer_phone": order.customer_phone,
                    "origin": order.origin,
                    "destination": order.destination,
                    "cargo_type": order.cargo_type,
                    "weight": order.weight,
                    "pickup_date": order.pickup_date.isoformat() if order.pickup_date else None,
                    "delivery_date": order.delivery_date.isoformat() if order.delivery_date else None,
                    "load_total": order.load_total,
                    "load_currency": order.load_currency,
                }
            })

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
            return JsonResponse({"error": f"Failed to process PDF: {str(e)}"}, status=500)

    except ValidationError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        logger.error(f"Error processing upload: {str(e)}", exc_info=True)
        return JsonResponse({"error": "An unexpected error occurred"}, status=500)

@login_required
@require_http_methods(["POST"])
def order_validate(request):
    """API endpoint to validate order data before creation."""
    try:
        data = request.POST.dict()
        errors = {}
        
        # Required fields validation
        required = ['order_number', 'customer_name', 'origin', 'destination', 'pickup_date', 'delivery_date', 'load_total']
        for field in required:
            if not data.get(field):
                errors[field] = 'This field is required'
        
        if errors:
            return JsonResponse({'valid': False, 'errors': errors}, status=400)

        # Order number uniqueness
        if Order.objects.filter(order_number=data['order_number'], tenant=request.user.profile.tenant).exists():
            errors['order_number'] = 'Order number already exists'
            return JsonResponse({'valid': False, 'errors': errors}, status=400)

        # Date validation
        try:
            pickup = timezone.datetime.strptime(data['pickup_date'], '%Y-%m-%d').date()
            delivery = timezone.datetime.strptime(data['delivery_date'], '%Y-%m-%d').date()
            if pickup > delivery:
                errors['delivery_date'] = 'Must be after pickup date'
        except ValueError:
            errors['dates'] = 'Use YYYY-MM-DD format'

        # Load total validation
        try:
            if float(data['load_total']) <= 0:
                errors['load_total'] = 'Must be greater than 0'
        except ValueError:
            errors['load_total'] = 'Invalid number'

        if errors:
            return JsonResponse({'valid': False, 'errors': errors}, status=400)

        return JsonResponse({'valid': True, 'message': 'Order data is valid'})

    except Exception as e:
        logger.error(f"Error validating order: {str(e)}", exc_info=True)
        return JsonResponse({'valid': False, 'error': 'Internal server error'}, status=500)

@login_required
@require_http_methods(["GET"])
def available_assignments(request):
    """Get available assignments for a driver."""
    try:
        # Get assignments that are available for the driver
        assignments = Trip.objects.filter(
            tenant=request.user.profile.tenant,
            status="Available",
        ).select_related("order", "driver", "truck")

        data = []
        for assignment in assignments:
            data.append({
                "id": str(assignment.id),
                "order_number": assignment.order.order_number if assignment.order else None,
                "pickup_date": assignment.pickup_date.strftime("%Y-%m-%d") if assignment.pickup_date else None,
                "delivery_date": assignment.delivery_date.strftime("%Y-%m-%d") if assignment.delivery_date else None,
                "origin": assignment.origin,
                "destination": assignment.destination,
                "status": assignment.status,
                "driver": str(assignment.driver) if assignment.driver else None,
                "truck": str(assignment.truck) if assignment.truck else None,
            })

        return JsonResponse({"assignments": data})

    except Exception as e:
        logger.error(f"Error getting available assignments: {str(e)}", exc_info=True)
        return JsonResponse({"error": "An unexpected error occurred"}, status=500)

@login_required
@require_http_methods(["POST"])
def trip_status_update(request):
    """Update trip status."""
    try:
        trip_id = request.POST.get('trip_id')
        new_status = request.POST.get('status')

        if not trip_id or not new_status:
            return JsonResponse({"error": "Trip ID and status are required"}, status=400)

        trip = Trip.objects.get(id=trip_id, tenant=request.user.profile.tenant)
        trip.status = new_status
        trip.save()

        return JsonResponse({"success": True, "message": f"Trip status updated to {new_status}"})

    except Trip.DoesNotExist:
        return JsonResponse({"error": "Trip not found"}, status=404)
    except Exception as e:
        logger.error(f"Error updating trip status: {str(e)}", exc_info=True)
        return JsonResponse({"error": "An unexpected error occurred"}, status=500)

@login_required
@require_http_methods(["POST"])
def assignment_status_update(request):
    """API endpoint to update assignment status."""
    try:
        assignment_id = request.POST.get('assignment_id')
        new_status = request.POST.get('status')

        if not assignment_id or not new_status:
            return JsonResponse({
                'valid': False,
                'errors': {'general': 'Assignment ID and status are required'}
            }, status=400)

        # Get the assignment
        assignment = DriverTruckAssignment.objects.select_related(
            'driver', 'truck', 'trip'
        ).get(
            id=assignment_id,
            tenant=request.user.profile.tenant
        )

        # Validate status transition
        if new_status not in dict(AssignmentStatus.choices):
            return JsonResponse({
                'valid': False,
                'errors': {'status': f'Invalid status: {new_status}'}
            }, status=400)

        old_status = assignment.status
        assignment.status = new_status
        assignment.save()

        # Create log entry if the model has logging capability
        if hasattr(assignment, 'logs'):
            assignment.logs.create(
                action='STATUS_CHANGE',
                message=f'Status changed from {old_status} to {new_status}',
                created_by=request.user,
                tenant=assignment.tenant
            )

        # Update related trip if exists
        if assignment.trip:
            if new_status == AssignmentStatus.ON_DUTY:
                assignment.trip.status = TripStatus.IN_PROGRESS
            elif new_status == AssignmentStatus.OFF_DUTY:
                assignment.trip.status = TripStatus.COMPLETED
            elif new_status == AssignmentStatus.CANCELLED:
                assignment.trip.status = TripStatus.CANCELLED
            assignment.trip.save()

        return JsonResponse({
            'valid': True,
            'message': f'Assignment status updated to {new_status}',
            'data': {
                'assignment_id': str(assignment.id),
                'status': new_status,
                'trip': {
                    'id': str(assignment.trip.id),
                    'status': assignment.trip.status
                } if assignment.trip else None,
                'driver': {
                    'id': str(assignment.driver.id),
                    'name': f"{assignment.driver.first_name} {assignment.driver.last_name}"
                } if assignment.driver else None,
                'truck': {
                    'id': str(assignment.truck.id),
                    'unit_number': assignment.truck.unit
                } if assignment.truck else None
            }
        })

    except DriverTruckAssignment.DoesNotExist:
        return JsonResponse({
            'valid': False,
            'errors': {'assignment_id': 'Assignment not found'}
        }, status=404)
    except Exception as e:
        logger.error(f"Error updating assignment status: {str(e)}", exc_info=True)
        return JsonResponse({
            'valid': False,
            'error': 'Internal server error'
        }, status=500)

@login_required
@require_http_methods(["GET"])
def available_resources(request):
    """Get available drivers and trucks for assignment."""
    try:
        tenant = request.user.profile.tenant
        
        # Get trip_id from query parameters
        trip_id = request.GET.get('trip_id')
        
        # If trip_id is provided, get dates from the trip
        if trip_id:
            try:
                trip = Trip.objects.select_related('order').get(
                    id=trip_id,
                    tenant=tenant
                )
                
                start_date = trip.order.pickup_date or timezone.now()
                end_date = trip.order.delivery_date
                if not end_date and trip.estimated_duration:
                    end_date = start_date + trip.estimated_duration
            except Trip.DoesNotExist:
                return JsonResponse({"error": "Trip not found"}, status=404)
        else:
            # Get dates from query parameters if no trip_id
            start_date_str = request.GET.get('start_date')
            end_date_str = request.GET.get('end_date')
            
            if not start_date_str:
                return JsonResponse({"error": "Start date is required when trip_id is not provided"}, status=400)
                
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%dT%H:%M")
                end_date = datetime.strptime(end_date_str, "%Y-%m-%dT%H:%M") if end_date_str else None
            except ValueError:
                return JsonResponse({"error": "Invalid date format"}, status=400)
        
        # Get all active drivers with correct case for status values
        drivers = Driver.objects.filter(
            tenant=tenant,
            is_active=True,
            driveremployment__employment_status='active',
            driveremployment__duty_status='available'
        ).select_related('carrier', 'driveremployment')
        
        # Get all active trucks with correct case for status values
        trucks = Truck.objects.filter(
            tenant=tenant,
            status='active',
            is_active=True,
            duty_status='available'
        ).select_related('carrier')
        
        # Exclude drivers and trucks that have conflicting assignments
        if end_date:
            conflicting_assignments = DriverTruckAssignment.objects.filter(
                tenant=tenant,
                status__in=['assigned', 'on_duty'],  # Fix case for assignment status
                start_date__lt=end_date,
                end_date__gt=start_date
            )
        else:
            conflicting_assignments = DriverTruckAssignment.objects.filter(
                tenant=tenant,
                status__in=['assigned', 'on_duty'],  # Fix case for assignment status
                start_date__lt=start_date + timezone.timedelta(days=365),  # Default to one year
                end_date__gt=start_date
            )
            
        busy_driver_ids = conflicting_assignments.values_list('driver_id', flat=True)
        busy_truck_ids = conflicting_assignments.values_list('truck_id', flat=True)
        
        available_drivers = drivers.exclude(id__in=busy_driver_ids)
        available_trucks = trucks.exclude(id__in=busy_truck_ids)
        
        # Prepare response data with carrier information
        driver_data = [{
            'id': str(driver.id),
            'first_name': driver.first_name,
            'last_name': driver.last_name,
            'carrier': {
                'id': str(driver.carrier.id),
                'name': driver.carrier.name
            } if driver.carrier else None
        } for driver in available_drivers]
        
        truck_data = [{
            'id': str(truck.id),
            'unit': truck.unit,
            'make': truck.make,
            'model': truck.model,
            'carrier': {
                'id': str(truck.carrier.id),
                'name': truck.carrier.name
            } if truck.carrier else None
        } for truck in available_trucks]
        
        return JsonResponse({
            'drivers': driver_data,
            'trucks': truck_data
        })
        
    except Exception as e:
        logger.error(f"Error fetching available resources: {str(e)}", exc_info=True)
        return JsonResponse({"error": "An unexpected error occurred"}, status=500)