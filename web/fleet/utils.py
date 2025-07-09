import os
import secrets
import logging
import json
from datetime import datetime
from uuid import UUID
from pathlib import Path  # type: ignore
from django.conf import settings  # type: ignore
from django.contrib.contenttypes.models import ContentType  # type: ignore
from django.core.exceptions import ValidationError  # type: ignore
from contrib.aws import s3_utils
from contrib.extraction.document.driver_license import (
    extract_license_info,
    DriverLicenseExtraction,
)
from fleet.models import Driver, DriverLicense, DriverEmployment
from tenant.models import Tenant
from subscriptions.models import QuotaService, UsageLog
from contrib.extraction.document.utils import calculate_file_size_mb
from typing import Tuple, Dict, Any, Optional
from django.core.files.storage import default_storage
from django.utils import timezone

logger = logging.getLogger("django")


def ensure_tmp_directories() -> Tuple[str, str]:
    """Ensure temporary directories exist for file processing"""
    tmp_dir = os.path.join(settings.BASE_DIR, "tmp")
    documents_dir = os.path.join(tmp_dir, "documents")
    os.makedirs(tmp_dir, exist_ok=True)
    os.makedirs(documents_dir, exist_ok=True)
    return tmp_dir, documents_dir


def get_file_path(tenant_id: str, file_type: str, filename: str) -> str:
    """Generate standardized file path for storage"""
    return f"{settings.ENV}/{tenant_id}/{file_type}/{filename}"


def save_uploaded_file(file, tenant_id: str, file_type: str) -> Tuple[str, str]:
    """Save uploaded file and return filepath and filename"""
    filename = f"{file.name}"
    file_path = get_file_path(tenant_id, file_type, filename)
    
    with default_storage.open(file_path, 'wb+') as destination:
        for chunk in file.chunks():
            destination.write(chunk)
    
    return file_path, filename


def format_phone_number(phone: str) -> str:
    """Format phone number to standard format"""
    # Remove all non-numeric characters
    numbers_only = ''.join(filter(str.isdigit, phone))
    
    # Ensure we have a valid number of digits
    if len(numbers_only) == 10:
        return f"+1{numbers_only}"
    elif len(numbers_only) == 11 and numbers_only.startswith('1'):
        return f"+{numbers_only}"
    return phone


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse date string to datetime object"""
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def validate_vin(vin: str) -> bool:
    """Validate Vehicle Identification Number"""
    if not vin or len(vin) != 17:
        return False
    
    # Add more VIN validation rules as needed
    return True


def calculate_truck_capacity(weight: float, trailer_capacity: str) -> Dict[str, Any]:
    """Calculate truck capacity details"""
    try:
        max_weight = float(weight)
        available_capacity = {
            'weight': max_weight,
            'trailer_capacity': trailer_capacity,
            'unit': 'kg'
        }
        return available_capacity
    except (ValueError, TypeError):
        return {
            'weight': 0,
            'trailer_capacity': '',
            'unit': 'kg'
        }


def format_license_number(license_number: str) -> str:
    """Format license number to standard format"""
    # Remove spaces and special characters
    clean_number = ''.join(filter(str.isalnum, license_number))
    return clean_number.upper()


def get_driver_status(hire_date: datetime, termination_date: Optional[datetime]) -> str:
    """Get driver's current employment status"""
    now = timezone.now()
    
    if not hire_date:
        return "PENDING"
    
    if termination_date and termination_date <= now:
        return "TERMINATED"
    
    if hire_date > now:
        return "SCHEDULED"
    
    return "ACTIVE"


def extract_driver_license_workflow(s3_key: str, tenant_id: UUID):
    """Process driver license file synchronously.
    
    Args:
        s3_key: S3 key of the uploaded file
        tenant_id: UUID of the tenant
        
    Returns:
        Tuple of (driver_license_id, driver_id)
    """
    # Ensure tmp directories exist
    tmp_dir, documents_dir = ensure_tmp_directories()

    filename = s3_key.split("/")[-1]
    local_path = os.path.join(
        tmp_dir,
        "documents",
        f"{secrets.token_urlsafe(6)}_{filename}",
    )

    try:
        # Get tenant instance
        tenant = Tenant.objects.get(id=tenant_id)
        quota_service = QuotaService(tenant)

        # Download and check file size
        s3_download_success = s3_utils.download_file(s3_key, local_path)
        if not s3_download_success:
            raise Exception(f"Failed to download file from S3: {s3_key}")

        file_size_mb = calculate_file_size_mb(local_path)
        logger.info(f"Processing license file of size: {file_size_mb}MB")

        # Check storage quota
        current_storage = quota_service.usage_period.storage_used_mb
        storage_limit = quota_service.get_limit("storage_limit_mb")
        if current_storage + file_size_mb > storage_limit:
            raise ValidationError(
                f"Storage quota would be exceeded. Current: {current_storage}MB, Limit: {storage_limit}MB"
            )

        # Check license processing quota
        if quota_service.usage_period.licenses_processed >= quota_service.get_limit(
            "monthly_license_limit"
        ):
            raise ValidationError("Monthly license processing limit reached")

        # Check estimated token quota
        estimated_tokens = file_size_mb * 1000  # rough estimate
        if (
            quota_service.usage_period.tokens_used + estimated_tokens
            > quota_service.get_limit("monthly_token_limit")
        ):
            raise ValidationError("Monthly token limit would likely be exceeded")

        # Process document after quota checks
        try:
            logger.info(f"Extracting license info from {local_path}")
            response, token_usage = extract_license_info(local_path)
            logger.info("License info extraction completed successfully")
        except Exception as e:
            logger.error(f"Error extracting license info: {str(e)}", exc_info=True)
            raise ValidationError(f"License extraction failed: {str(e)}")

        # Check token quota
        total_tokens = token_usage["total_tokens"]
        if (
            quota_service.usage_period.tokens_used + total_tokens
            > quota_service.get_limit("monthly_token_limit")
        ):
            raise ValidationError("Monthly token limit would be exceeded")

        # Extract the actual license data from the response
        if not response.choices or not response.choices[0].message.content:
            raise ValueError("No content in response choices")

        # Get the string content and try to parse it as JSON
        license_data_str = response.choices[0].message.content
        try:
            license_data = json.loads(license_data_str)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON response, attempting string parsing")
            lines = license_data_str.split("\n")
            license_data = {}
            for line in lines:
                if ":" in line:
                    key, value = line.split(":", 1)
                    license_data[key.strip().lower().replace(" ", "_")] = value.strip()

        # Parse response into Pydantic model
        try:
            driver_license_object = DriverLicenseExtraction(
                name=str(license_data.get("name", "")),
                license_number=str(license_data.get("license_number", "")),
                date_of_birth=str(license_data.get("date_of_birth", "")),
                issued_date=str(license_data.get("issued_date", "")),
                expiry_date=str(license_data.get("expiry_date", "")),
                gender=str(license_data.get("gender", "")),
                address=str(license_data.get("address", "")),
                country=str(license_data.get("country", "")),
                province=str(license_data.get("province", "")),
                state=str(license_data.get("state", "")),
            )
        except Exception as e:
            logger.error(f"Error parsing driver license data: {e}")
            logger.error(f"Raw license data: {license_data_str}")
            raise

        issue_date = parse_date(driver_license_object.issued_date)
        expiry_date = parse_date(driver_license_object.expiry_date)
        dob = parse_date(driver_license_object.date_of_birth)

        # Create or update DriverLicense
        driver_license, dl_created = DriverLicense.objects.update_or_create(
            license_number=driver_license_object.license_number,
            tenant=tenant,
            defaults={
                "name": driver_license_object.name,
                "date_of_birth": dob,
                "issued_date": issue_date,
                "expiry_date": expiry_date,
                "gender": driver_license_object.gender,
                "address": driver_license_object.address,
                "country": driver_license_object.country,
                "province": driver_license_object.province,
                "state": driver_license_object.state,
                "license_type": getattr(driver_license_object, 'license_type', None),
                "conditions": getattr(driver_license_object, 'conditions', None),
                "license_class": getattr(driver_license_object, 'license_class', None),
                "public_safety_commission": getattr(driver_license_object, 'public_safety_commission', None),
                "completion_tokens": token_usage["completion_tokens"],
                "prompt_tokens": token_usage["prompt_tokens"],
                "total_tokens": token_usage["total_tokens"],
                "llm_model_name": response.model,
                "uploaded_file_name": filename,
                "file_save_path": s3_key,
            },
        )

        # Log usage after driver license is created
        usage_log = UsageLog.objects.create(
            tenant=tenant,
            usage_period=quota_service.usage_period,
            feature="license_processing",
            tokens_used=total_tokens,
            storage_delta_mb=file_size_mb,
            content_type=ContentType.objects.get_for_model(DriverLicense),
            object_id=driver_license.id,
        )
        logger.debug(f"{usage_log=}")
        # Update usage period totals
        quota_service.usage_period.licenses_processed += 1
        quota_service.usage_period.tokens_used += total_tokens
        quota_service.usage_period.storage_used_mb += file_size_mb
        quota_service.usage_period.save()

        # Check thresholds and create alerts
        quota_service.check_limit_thresholds()

        # Process name parts
        name = driver_license_object.name.strip()
        if name:
            name_parts = name.split()
            first_name = name_parts[0]
            last_name = name_parts[-1] if len(name_parts) > 1 else ""
        else:
            first_name = ""
            last_name = ""
            logger.warning("Empty name received from license extraction")

        # Build complete address
        address_parts = []
        if driver_license_object.address:
            address_parts.append(driver_license_object.address)
        if driver_license_object.state:
            address_parts.append(f"State: {driver_license_object.state}")
        if driver_license_object.province:
            address_parts.append(f"Province: {driver_license_object.province}")
        if driver_license_object.country:
            address_parts.append(f"Country: {driver_license_object.country}")
        
        complete_address = "\n".join(filter(None, address_parts))

        # Get or create carrier
        carrier = tenant.carrier_set.first()
        if not carrier:
            raise ValueError("No carrier found for tenant")

        # Create or update Driver
        driver, driver_created = Driver.objects.update_or_create(
            drivers_license=driver_license,
            tenant=tenant,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
                "address": complete_address,
                "carrier": carrier,
                "employee_id": f"EMP-{driver_license.id}",  # Generate employee ID from license
                "hire_date": timezone.now().date(),  # Set hire date to today
                "license_number": driver_license.license_number,  # Copy from license
                "date_of_birth": driver_license.date_of_birth.date() if driver_license.date_of_birth else None,
                "country": driver_license.country,
                "state": driver_license.state,
            },
        )

        # Create or update DriverEmployment
        DriverEmployment.objects.update_or_create(
            driver=driver,
            defaults={
                "employment_status": "active",
                "duty_status": "available",
            }
        )

        logger.info(
            f"Successfully processed driver license. DL Created: {dl_created}, Driver Created: {driver_created}"
        )

        return driver_license.id, driver.id

    except ValidationError as e:
        logger.error(f"Validation error in driver license extraction: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error in driver license extraction workflow: {e}", exc_info=True)
        raise

    finally:
        # Clean up temporary file
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception as e:
                logger.warning(f"Failed to cleanup temporary file: {str(e)}")


def extract_driver_license_info(file_path: str) -> Tuple[Any, Dict[str, int]]:
    """
    Extract information from a driver's license file
    
    Args:
        file_path: Path to the license file (image or PDF)
        
    Returns:
        Tuple containing:
        - Extracted license information object
        - Token usage dictionary
    """
    try:
        # Extract information using GPT-4 Vision
        response = extract_license_info(file_path)
        
        # For image files, we get a ParsedChatCompletion object
        # We need to get the actual DriverLicenseExtraction from the parsed field
        if hasattr(response, 'parsed'):
            license_info = response.parsed
        else:
            # For PDF files or direct responses
            license_info = response
        
        # Get token usage information
        token_usage = {
            "completion_tokens": getattr(response, 'completion_tokens', 0),
            "prompt_tokens": getattr(response, 'prompt_tokens', 0),
            "total_tokens": getattr(response, 'total_tokens', 397)  # Default if not available
        }
        
        return license_info, token_usage
        
    except Exception as e:
        logger.error(f"Error extracting license info: {str(e)}", exc_info=True)
        raise


def map_driver_data(license_info: Any, driver_license: DriverLicense, tenant: Any) -> Driver:
    """
    Maps driver license information to a Driver model instance.
    Creates or updates a Driver based on the license information.
    """
    try:
        # Extract name components
        name_parts = license_info.name.split()
        first_name = name_parts[0]
        last_name = name_parts[-1]
        middle_name = " ".join(name_parts[1:-1]) if len(name_parts) > 2 else None

        # Build complete address
        address_parts = []
        if hasattr(license_info, 'address') and license_info.address:
            address_parts.append(license_info.address)
        if hasattr(license_info, 'state') and license_info.state:
            address_parts.append(f"State: {license_info.state}")
        if hasattr(license_info, 'province') and license_info.province:
            address_parts.append(f"Province: {license_info.province}")
        if hasattr(license_info, 'country') and license_info.country:
            address_parts.append(f"Country: {license_info.country}")
        
        complete_address = "\n".join(filter(None, address_parts))

        # Get or create carrier (assuming this is still needed)
        carrier = None
        if hasattr(license_info, 'carrier'):
            carrier = license_info.carrier

        # Parse date of birth
        dob = None
        if driver_license.date_of_birth:
            try:
                if isinstance(driver_license.date_of_birth, str):
                    # Try parsing the string as a date
                    parsed_date = datetime.strptime(driver_license.date_of_birth, '%Y-%m-%d')
                    dob = parsed_date.date() if parsed_date else None
                elif isinstance(driver_license.date_of_birth, datetime):
                    dob = driver_license.date_of_birth.date()
            except Exception as e:
                logger.warning(f"Failed to parse date of birth: {e}")

        # Set current date for hire_date
        current_date = timezone.now()

        # Try to find existing driver by license number
        try:
            existing_driver = Driver.objects.get(license_number=driver_license.license_number)
            # Update the existing driver's license reference
            existing_driver.drivers_license = driver_license
            existing_driver.save()
            driver = existing_driver
            logger.info(f"Updated existing driver with license number {driver_license.license_number}")
        except Driver.DoesNotExist:
            # Create new driver if no existing driver found
            driver = Driver.objects.create(
                first_name=first_name,
                last_name=last_name,
                address=complete_address,
                carrier=carrier,
                employee_id=f"EMP-{driver_license.id}",  # Generate employee ID from license
                hire_date=current_date.date(),  # Set hire date to today
                joining_date=current_date,  # Set joining date to now
                still_working=True,  # Set still_working to True for new drivers
                license_number=driver_license.license_number,  # Copy from license
                date_of_birth=dob,
                country=driver_license.country,
                state=driver_license.state,
                drivers_license=driver_license,
                tenant=tenant,
            )
            logger.info(f"Created new driver with license number {driver_license.license_number}")
        
        # Create or update DriverEmployment
        DriverEmployment.objects.update_or_create(
            driver=driver,
            defaults={
                "employment_status": "active",
                "duty_status": "available",
            }
        )
        
        return driver

    except Exception as e:
        logger.error(f"Error mapping driver data: {str(e)}", exc_info=True)
        raise
