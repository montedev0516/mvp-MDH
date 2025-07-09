"""Utility functions for the dispatch app."""

import os
import logging
import secrets
from typing import Final, Optional, Tuple, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta
from dateutil import parser as date_parser
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from contrib.aws import s3_utils
from contrib.extraction.document.invoice import extract_invoice, MODELS, TripResponse
from contrib.file_reader import open_pdf
from tenant.models import Tenant
from dispatch.models import (
    Order,
    Trip,
    TripStatus,
    DispatchStatus,
    OrderStatus,
    StatusHistory
)
from fleet.models import Customer, Driver, Truck
from django.contrib.contenttypes.models import ContentType
from subscriptions.models import QuotaService, UsageLog
from contrib.extraction.document.utils import calculate_file_size_mb

# Constants
TASK_MAX_RETRIES: Final[int] = 32
TASK_RETRY_BACKOFF: Final[int] = 100
TASK_RETRY_BACKOFF_MAX: Final[int] = 1600

logger = logging.getLogger("django")


def extract(filepath: str) -> Tuple[Dict[str, Any], Dict[str, int], str]:
    """
    Extract data from PDF file.
    
    Args:
        filepath: Path to the PDF file
        
    Returns:
        Tuple containing:
        - Dictionary of extracted order details
        - Dictionary of token usage statistics
        - String containing extracted text pages
    """
    try:
        pages, num_pages = open_pdf(filepath)
        extracted_response = extract_invoice(pages, model=MODELS.GPT4o_16k.value)
        logger.info(f"👏Extracted response from {num_pages} pages")
        
        order_details = extracted_response.choices[0].message.parsed.model_dump()
        token_usage = extracted_response.usage.model_dump()
        
        return order_details, token_usage, pages
        
    except Exception as e:
        logger.error(f"🔥Error extracting data from PDF: {str(e)}")
        raise


def parse_weight(weight_str: Optional[str]) -> Optional[float]:
    """
    Parse weight string to float value.
    
    Args:
        weight_str: Weight string (e.g. "45000.0 lb", "20.5 kg")
        
    Returns:
        Weight value in float or None if invalid
    """
    if not weight_str:
        return None
        
    try:
        # Extract numeric value using regex
        import re
        match = re.search(r'([\d,.]+)', weight_str)
        if not match:
            return None
            
        # Remove commas and convert to float
        weight_value = float(match.group(1).replace(',', ''))
        
        # Convert to pounds if in kg
        if 'kg' in weight_str.lower():
            weight_value *= 2.20462  # Convert kg to lb
            
        return weight_value
        
    except (ValueError, TypeError, AttributeError) as e:
        logger.warning(f"Error parsing weight {weight_str}: {str(e)}")
        return None


def map_order(order_details: Dict[str, Any], tenant: Tenant, s3_key: str) -> Order:
    """
    Map extracted data to Order model.
    
    Args:
        order_details: Dictionary containing extracted order details
        tenant: Tenant instance
        s3_key: S3 key of the uploaded file
        
    Returns:
        Created Order instance
    """
    try:
        with transaction.atomic():
            # Get customer details and phone numbers
            customer_data = order_details.get('customer_details', {})
            customer_phone = customer_data.get('customer_phone')
            
            # If customer phone is empty, try to find it in contact_numbers
            if not customer_phone and order_details.get('other_details', {}).get('contact_numbers'):
                # Look for a phone number associated with the customer name
                customer_name = customer_data.get('customer_name', '').lower()
                for phone in order_details.get('other_details', {}).get('contact_numbers', []):
                    # If we find a phone number near the customer name in the raw text, use it
                    if customer_name and customer_name in str(order_details.get('raw_text', '')).lower():
                        customer_phone = phone
                        break

            # Create or update customer
            customer, created = Customer.objects.get_or_create(
                tenant=tenant,
                email=customer_data.get('customer_email'),
                defaults={
                    'name': customer_data.get('customer_name'),
                    'phone': customer_phone,
                    'address': customer_data.get('customer_address')
                }
            )

            # Get load details
            load_details = order_details.get('total_load_details', {})
            
            # Parse weight value
            weight_str = order_details.get('freight_details', {}).get('freight_weight')
            weight = parse_weight(weight_str)
            
            # Get trip details
            trip_data = order_details.get('trips', [{}])[0]
            pickup_details = trip_data.get('pickup_details', {})
            delivery_details = trip_data.get('deliver_to_details', {})
            
            # Create order
            order = Order.objects.create(
                tenant=tenant,
                customer=customer,
                order_number=order_details.get('order_info', {}).get('order_id'),
                customer_name=customer_data.get('customer_name'),
                customer_address=customer_data.get('customer_address'),
                customer_email=customer_data.get('customer_email'),
                customer_phone=customer_phone,  # Use the potentially updated customer phone
                origin=pickup_details.get('pickup_address'),
                destination=delivery_details.get('delivery_address'),
                cargo_type=order_details.get('freight_details', {}).get('freight_type'),
                weight=weight,
                load_total=load_details.get('load_total'),
                load_currency=load_details.get('currency'),
                pickup_date=parse_date(pickup_details.get('pickup_date')),
                delivery_date=parse_date(delivery_details.get('delivery_date')),
                pdf=s3_key,
                status=OrderStatus.PENDING,
                remarks_or_special_instructions=order_details.get('remarks_or_special_instructions'),
                raw_extract=order_details,
                raw_text="",  # This will be filled by the extraction process
                completion_tokens=0,  # These will be filled by the extraction process
                prompt_tokens=0,
                total_tokens=0,
                llm_model_name=MODELS.GPT4o_16k.value,
                usage_details={},
                processed=False  # Set to False initially, will be set to True when dispatch is created
            )

            # Create status history with empty string for old_status
            StatusHistory.objects.create(
                content_type=ContentType.objects.get_for_model(Order),
                object_id=order.id,
                old_status="",  # Use empty string instead of None
                new_status=OrderStatus.PENDING,
                tenant=tenant
            )

            return order

    except Exception as e:
        logger.error(f"Error mapping order: {str(e)}")
        raise


def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """
    Parse date string to datetime object.
    
    Args:
        date_str: Date string to parse (expected format: MM/DD/YYYY)
        
    Returns:
        Parsed datetime object or None if invalid
    """
    if not date_str:
        return None
        
    try:
        # First try MM/DD/YYYY format
        parsed_date = datetime.strptime(date_str, '%m/%d/%Y')
        # Make timezone aware
        return timezone.make_aware(parsed_date)
    except (ValueError, TypeError):
        try:
            # Fallback to dateutil parser for other formats
            parsed_date = date_parser.parse(date_str)
            # Make timezone aware if it isn't already
            if timezone.is_naive(parsed_date):
                parsed_date = timezone.make_aware(parsed_date)
            return parsed_date
        except (ValueError, TypeError) as e:
            logger.warning(f"🙌Error parsing date {date_str}: {str(e)}")
            return None


def get_available_drivers(tenant: Tenant, start_date: datetime, end_date: datetime) -> Dict[UUID, Driver]:
    """
    Get drivers available for assignment during specified period.
    Uses SELECT FOR UPDATE to prevent race conditions.
    """
    from fleet.models import Driver, EmploymentStatus, DutyStatus
    from dispatch.models import DriverTruckAssignment, AssignmentStatus
    
    with transaction.atomic():
        # Get all active drivers for the tenant with locking
        available_drivers = Driver.objects.select_for_update().filter(
            tenant=tenant,
            is_active=True,
            driveremployment__employment_status=EmploymentStatus.ACTIVE,
            driveremployment__duty_status__in=[DutyStatus.AVAILABLE, DutyStatus.ON_DUTY]
        ).select_related('driveremployment', 'carrier')
        
        # Filter out drivers with conflicting assignments
        if end_date:
            conflicting_driver_ids = DriverTruckAssignment.objects.filter(
                driver__in=available_drivers,
                status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY],
                start_date__lt=end_date,
                end_date__gt=start_date,
                is_active=True
            ).values_list('driver_id', flat=True)
        else:
            # For open-ended assignments, check for any active assignments
            conflicting_driver_ids = DriverTruckAssignment.objects.filter(
                driver__in=available_drivers,
                status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY],
                end_date__isnull=True,
                is_active=True
            ).values_list('driver_id', flat=True)
        
        # Exclude drivers with conflicts
        available_drivers = available_drivers.exclude(id__in=conflicting_driver_ids)
        
        # Check driver qualifications and license validity
        qualified_drivers = {}
        for driver in available_drivers:
            # Check license validity
            if driver.is_license_valid():
                qualified_drivers[driver.id] = driver
            else:
                logger.warning(f"Driver {driver.get_full_name()} has invalid/expired license")
        
        return qualified_drivers


def get_available_trucks(tenant: Tenant, start_date: datetime, end_date: datetime) -> Dict[UUID, Truck]:
    """
    Get trucks available for assignment during specified period.
    Uses SELECT FOR UPDATE to prevent race conditions.
    """
    from fleet.models import Truck, TruckStatus, TruckDutyStatus
    from dispatch.models import DriverTruckAssignment, AssignmentStatus
    
    with transaction.atomic():
        # Get all active trucks for the tenant with locking
        available_trucks = Truck.objects.select_for_update().filter(
            tenant=tenant,
            is_active=True,
            status=TruckStatus.ACTIVE,
            duty_status__in=[TruckDutyStatus.AVAILABLE, TruckDutyStatus.ON_DUTY]
        ).select_related('carrier')
        
        # Filter out trucks with conflicting assignments
        if end_date:
            conflicting_truck_ids = DriverTruckAssignment.objects.filter(
                truck__in=available_trucks,
                status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY],
                start_date__lt=end_date,
                end_date__gt=start_date,
                is_active=True
            ).values_list('truck_id', flat=True)
        else:
            # For open-ended assignments, check for any active assignments
            conflicting_truck_ids = DriverTruckAssignment.objects.filter(
                truck__in=available_trucks,
                status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY],
                end_date__isnull=True,
                is_active=True
            ).values_list('truck_id', flat=True)
        
        # Exclude trucks with conflicts
        available_trucks = available_trucks.exclude(id__in=conflicting_truck_ids)
        
        # Return as dictionary for easy lookup
        return {truck.id: truck for truck in available_trucks}


def check_resource_availability_with_lock(driver_id: UUID, truck_id: UUID, start_date: datetime, end_date: datetime = None, exclude_assignment_id: UUID = None) -> Tuple[bool, str]:
    """
    Check if driver and truck are available for assignment with database locking.
    
    Args:
        driver_id: UUID of the driver
        truck_id: UUID of the truck  
        start_date: Assignment start date
        end_date: Assignment end date (optional)
        exclude_assignment_id: Assignment ID to exclude from conflict check
        
    Returns:
        Tuple of (is_available: bool, reason: str)
    """
    from fleet.models import Driver, Truck
    from dispatch.models import DriverTruckAssignment, AssignmentStatus
    
    with transaction.atomic():
        try:
            # Lock the driver and truck records
            driver = Driver.objects.select_for_update().get(id=driver_id)
            truck = Truck.objects.select_for_update().get(id=truck_id)
            
            # Check driver qualification for truck
            is_qualified, reason = driver.is_qualified_for_truck(truck)
            if not is_qualified:
                return False, reason
            
            # Check for conflicting assignments
            conflict_filter = {
                'status__in': [AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY],
                'is_active': True
            }
            
            if end_date:
                conflict_filter.update({
                    'start_date__lt': end_date,
                    'end_date__gt': start_date
                })
            else:
                conflict_filter.update({
                    'start_date__gte': start_date,
                    'end_date__isnull': True
                })
            
            # Check driver conflicts
            driver_conflicts = DriverTruckAssignment.objects.filter(
                driver=driver,
                **conflict_filter
            )
            
            if exclude_assignment_id:
                driver_conflicts = driver_conflicts.exclude(id=exclude_assignment_id)
                
            if driver_conflicts.exists():
                return False, f"Driver {driver.get_full_name()} has conflicting assignments"
            
            # Check truck conflicts  
            truck_conflicts = DriverTruckAssignment.objects.filter(
                truck=truck,
                **conflict_filter
            )
            
            if exclude_assignment_id:
                truck_conflicts = truck_conflicts.exclude(id=exclude_assignment_id)
                
            if truck_conflicts.exists():
                return False, f"Truck {truck.unit} has conflicting assignments"
            
            return True, "Resources are available"
            
        except (Driver.DoesNotExist, Truck.DoesNotExist) as e:
            return False, f"Resource not found: {str(e)}"
        except Exception as e:
            logger.error(f"Error checking resource availability: {str(e)}")
            return False, f"Error checking availability: {str(e)}"


def sync_related_statuses(dispatch_id: UUID, old_status: str, new_status: str, user=None) -> None:
    """
    Synchronize related model statuses when dispatch status changes.
    Enhanced version with comprehensive status monitoring.
    """
    from dispatch.models import Dispatch
    
    try:
        dispatch = Dispatch.objects.select_related(
            'order', 'trip', 'driver', 'truck'
        ).prefetch_related('assignments').get(id=dispatch_id)
        
        # Use the model's enhanced sync method
        dispatch.sync_related_statuses(old_status, user)
        
        logger.info(f"Successfully synced statuses for dispatch {dispatch.dispatch_id}: {old_status} → {new_status}")
        
    except Dispatch.DoesNotExist:
        logger.error(f"Dispatch {dispatch_id} not found for status sync")
    except Exception as e:
        logger.error(f"Error syncing statuses for dispatch {dispatch_id}: {str(e)}")
        raise


def detect_status_inconsistencies(tenant: Tenant) -> Dict[str, Any]:
    """
    Detect status inconsistencies across the dispatch system.
    
    Returns:
        Dictionary containing detected inconsistencies and suggested fixes
    """
    from dispatch.models import Dispatch, Order, Trip, DriverTruckAssignment
    from fleet.models import Driver, Truck
    
    inconsistencies = {
        'dispatch_order_mismatches': [],
        'dispatch_trip_mismatches': [],
        'assignment_resource_mismatches': [],
        'orphaned_assignments': [],
        'resource_conflicts': [],
        'summary': {}
    }
    
    try:
        # Check Dispatch-Order status consistency
        dispatches = Dispatch.objects.filter(tenant=tenant).select_related('order')
        for dispatch in dispatches:
            if dispatch.order:
                expected_order_status = None
                if dispatch.status in [DispatchStatus.IN_TRANSIT, DispatchStatus.DELIVERED]:
                    expected_order_status = OrderStatus.IN_PROGRESS
                elif dispatch.status == DispatchStatus.COMPLETED:
                    expected_order_status = OrderStatus.COMPLETED
                elif dispatch.status == DispatchStatus.CANCELLED:
                    expected_order_status = OrderStatus.CANCELLED
                
                if expected_order_status and dispatch.order.status != expected_order_status:
                    inconsistencies['dispatch_order_mismatches'].append({
                        'dispatch_id': str(dispatch.id),
                        'dispatch_status': dispatch.status,
                        'order_status': dispatch.order.status,
                        'expected_order_status': expected_order_status
                    })
        
        # Check Dispatch-Trip status consistency
        for dispatch in dispatches.filter(trip__isnull=False).select_related('trip'):
            expected_trip_status = None
            if dispatch.status == DispatchStatus.IN_TRANSIT:
                expected_trip_status = TripStatus.IN_PROGRESS
            elif dispatch.status in [DispatchStatus.DELIVERED, DispatchStatus.COMPLETED]:
                expected_trip_status = TripStatus.COMPLETED
            elif dispatch.status == DispatchStatus.CANCELLED:
                expected_trip_status = TripStatus.CANCELLED
            
            if expected_trip_status and dispatch.trip.status != expected_trip_status:
                inconsistencies['dispatch_trip_mismatches'].append({
                    'dispatch_id': str(dispatch.id),
                    'dispatch_status': dispatch.status,
                    'trip_status': dispatch.trip.status,
                    'expected_trip_status': expected_trip_status
                })
        
        # Check Assignment-Resource status consistency
        assignments = DriverTruckAssignment.objects.filter(
            tenant=tenant
        ).select_related('driver', 'driver__driveremployment', 'truck', 'dispatch')
        
        for assignment in assignments:
            issues = []
            
            # Check driver employment status
            if assignment.driver and hasattr(assignment.driver, 'driveremployment'):
                employment = assignment.driver.driveremployment
                if assignment.status in [AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY]:
                    if employment.duty_status not in [DutyStatus.ON_DUTY, DutyStatus.AVAILABLE]:
                        issues.append(f"Driver duty status is {employment.duty_status}, expected ON_DUTY or AVAILABLE")
                
            # Check truck status
            if assignment.truck:
                if assignment.status in [AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY]:
                    if assignment.truck.duty_status not in [TruckDutyStatus.ON_DUTY, TruckDutyStatus.AVAILABLE]:
                        issues.append(f"Truck duty status is {assignment.truck.duty_status}, expected ON_DUTY or AVAILABLE")
            
            if issues:
                inconsistencies['assignment_resource_mismatches'].append({
                    'assignment_id': str(assignment.id),
                    'assignment_status': assignment.status,
                    'issues': issues
                })
        
        # Check for orphaned assignments (assignments without valid dispatch)
        orphaned = DriverTruckAssignment.objects.filter(
            tenant=tenant,
            dispatch__isnull=True,
            status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY]
        )
        
        for assignment in orphaned:
            inconsistencies['orphaned_assignments'].append({
                'assignment_id': str(assignment.id),
                'driver': assignment.driver.get_full_name() if assignment.driver else None,
                'truck': str(assignment.truck.unit) if assignment.truck else None,
                'status': assignment.status
            })
        
        # Check for resource conflicts (same resource assigned to multiple active assignments)
        from django.db.models import Count
        
        # Driver conflicts
        driver_conflicts = DriverTruckAssignment.objects.filter(
            tenant=tenant,
            status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY],
            is_active=True
        ).values('driver').annotate(
            count=Count('id')
        ).filter(count__gt=1)
        
        for conflict in driver_conflicts:
            conflicting_assignments = DriverTruckAssignment.objects.filter(
                driver_id=conflict['driver'],
                status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY],
                is_active=True
            ).select_related('driver', 'dispatch')
            
            inconsistencies['resource_conflicts'].append({
                'type': 'driver',
                'resource_id': conflict['driver'],
                'assignments': [
                    {
                        'assignment_id': str(a.id),
                        'dispatch_id': str(a.dispatch.id) if a.dispatch else None,
                        'status': a.status
                    } for a in conflicting_assignments
                ]
            })
        
        # Truck conflicts
        truck_conflicts = DriverTruckAssignment.objects.filter(
            tenant=tenant,
            status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY],
            is_active=True
        ).values('truck').annotate(
            count=Count('id')
        ).filter(count__gt=1)
        
        for conflict in truck_conflicts:
            conflicting_assignments = DriverTruckAssignment.objects.filter(
                truck_id=conflict['truck'],
                status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY],
                is_active=True
            ).select_related('truck', 'dispatch')
            
            inconsistencies['resource_conflicts'].append({
                'type': 'truck',
                'resource_id': conflict['truck'],
                'assignments': [
                    {
                        'assignment_id': str(a.id),
                        'dispatch_id': str(a.dispatch.id) if a.dispatch else None,
                        'status': a.status
                    } for a in conflicting_assignments
                ]
            })
        
        # Generate summary
        inconsistencies['summary'] = {
            'total_issues': (
                len(inconsistencies['dispatch_order_mismatches']) +
                len(inconsistencies['dispatch_trip_mismatches']) +
                len(inconsistencies['assignment_resource_mismatches']) +
                len(inconsistencies['orphaned_assignments']) +
                len(inconsistencies['resource_conflicts'])
            ),
            'critical_issues': len(inconsistencies['resource_conflicts']),
            'generated_at': timezone.now().isoformat()
        }
        
        logger.info(f"Status inconsistency check completed for tenant {tenant.id}. Found {inconsistencies['summary']['total_issues']} issues.")
        
    except Exception as e:
        logger.error(f"Error detecting status inconsistencies: {str(e)}")
        inconsistencies['error'] = str(e)
    
    return inconsistencies


def fix_status_inconsistencies(tenant: Tenant, inconsistencies: Dict[str, Any] = None, dry_run: bool = True) -> Dict[str, Any]:
    """
    Attempt to fix detected status inconsistencies.
    
    Args:
        tenant: Tenant instance
        inconsistencies: Previously detected inconsistencies (if None, will detect first)
        dry_run: If True, only simulate fixes without making changes
        
    Returns:
        Dictionary containing fix results
    """
    if inconsistencies is None:
        inconsistencies = detect_status_inconsistencies(tenant)
    
    fix_results = {
        'fixes_applied': [],
        'fixes_failed': [],
        'dry_run': dry_run,
        'summary': {}
    }
    
    if dry_run:
        logger.info("Running status fix in DRY RUN mode - no changes will be made")
    
    try:
        # Fix dispatch-order mismatches
        for mismatch in inconsistencies.get('dispatch_order_mismatches', []):
            try:
                if not dry_run:
                    from dispatch.models import Dispatch
                    dispatch = Dispatch.objects.get(id=mismatch['dispatch_id'])
                    old_status = dispatch.order.status
                    dispatch.order.status = mismatch['expected_order_status']
                    dispatch.order.save()
                    dispatch.order.log_status_change(old_status, mismatch['expected_order_status'])
                
                fix_results['fixes_applied'].append({
                    'type': 'dispatch_order_mismatch',
                    'dispatch_id': mismatch['dispatch_id'],
                    'action': f"Updated order status from {mismatch['order_status']} to {mismatch['expected_order_status']}"
                })
                
            except Exception as e:
                fix_results['fixes_failed'].append({
                    'type': 'dispatch_order_mismatch',
                    'dispatch_id': mismatch['dispatch_id'],
                    'error': str(e)
                })
        
        # Fix resource conflicts by deactivating older assignments
        for conflict in inconsistencies.get('resource_conflicts', []):
            try:
                if not dry_run:
                    from dispatch.models import DriverTruckAssignment
                    # Keep the most recent assignment, deactivate others
                    assignments = DriverTruckAssignment.objects.filter(
                        id__in=[a['assignment_id'] for a in conflict['assignments']]
                    ).order_by('-created_at')
                    
                    for assignment in assignments[1:]:  # Skip the first (most recent)
                        old_status = assignment.status
                        assignment.status = AssignmentStatus.CANCELLED
                        assignment.is_active = False
                        assignment.save()
                        assignment.log_status_change(old_status, AssignmentStatus.CANCELLED)
                
                fix_results['fixes_applied'].append({
                    'type': 'resource_conflict',
                    'resource_type': conflict['type'],
                    'resource_id': conflict['resource_id'],
                    'action': f"Deactivated {len(conflict['assignments']) - 1} conflicting assignments"
                })
                
            except Exception as e:
                fix_results['fixes_failed'].append({
                    'type': 'resource_conflict',
                    'resource_id': conflict['resource_id'],
                    'error': str(e)
                })
        
        fix_results['summary'] = {
            'total_fixes_attempted': len(fix_results['fixes_applied']) + len(fix_results['fixes_failed']),
            'successful_fixes': len(fix_results['fixes_applied']),
            'failed_fixes': len(fix_results['fixes_failed']),
            'fixed_at': timezone.now().isoformat()
        }
        
        logger.info(f"Status fix completed for tenant {tenant.id}. Applied {len(fix_results['fixes_applied'])} fixes, {len(fix_results['fixes_failed'])} failed.")
        
    except Exception as e:
        logger.error(f"Error fixing status inconsistencies: {str(e)}")
        fix_results['error'] = str(e)
    
    return fix_results
