from celery import shared_task
import pandas as pd
import logging
from django.core.cache import cache
from django.core.exceptions import ValidationError
from expense.models import BVD, AccountPayableStatus
from fleet.models import Truck
from django.db import transaction
from datetime import datetime, timedelta
import pytz
from django.conf import settings

logger = logging.getLogger("django")

@shared_task(bind=True)
def process_bvd_file(self, file_path, tenant_id, batch_id):
    """
    Process BVD file in background
    
    Args:
        file_path: Path to the uploaded file
        tenant_id: ID of the tenant
        batch_id: Unique ID for this import batch
    """
    try:
        # Initialize progress tracking
        cache.set(f"bvd_import_{batch_id}_status", {
            "status": "PROCESSING",
            "total": 0,
            "processed": 0,
            "success": 0,
            "errors": 0,
            "error_details": []
        }, timeout=3600)  # Cache for 1 hour

        # Read file
        file_extension = file_path.split(".")[-1].lower()
        if file_extension == "csv":
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        # Clean column names
        df.columns = df.columns.str.strip()

        # Update total records
        total_records = len(df)
        cache.set(f"bvd_import_{batch_id}_status", {
            "status": "PROCESSING",
            "total": total_records,
            "processed": 0,
            "success": 0,
            "errors": 0,
            "error_details": []
        }, timeout=3600)

        # Process in batches of 100
        batch_size = 100
        success_count = 0
        error_count = 0
        error_details = []

        for start_idx in range(0, len(df), batch_size):
            end_idx = min(start_idx + batch_size, len(df))
            batch_df = df[start_idx:end_idx]
            
            with transaction.atomic():
                for _, row in batch_df.iterrows():
                    try:
                        # Process row
                        bvd_data = process_row(row, tenant_id)
                        
                        # Create and save BVD instance
                        bvd = BVD(**bvd_data)
                        bvd.full_clean()
                        bvd.save()
                        success_count += 1
                        
                    except Exception as e:
                        error_count += 1
                        error_details.append(f"Row {start_idx + _ + 2}: {str(e)}")
                        logger.error(f"Error processing row {start_idx + _ + 2}: {str(e)}")

            # Update progress
            cache.set(f"bvd_import_{batch_id}_status", {
                "status": "PROCESSING",
                "total": total_records,
                "processed": end_idx,
                "success": success_count,
                "errors": error_count,
                "error_details": error_details[-5:]  # Keep last 5 errors
            }, timeout=3600)

        # Set final status
        final_status = "COMPLETED" if error_count == 0 else "COMPLETED_WITH_ERRORS"
        cache.set(f"bvd_import_{batch_id}_status", {
            "status": final_status,
            "total": total_records,
            "processed": total_records,
            "success": success_count,
            "errors": error_count,
            "error_details": error_details[-5:]  # Keep last 5 errors
        }, timeout=3600)

        return {
            "status": final_status,
            "total": total_records,
            "success": success_count,
            "errors": error_count
        }

    except Exception as e:
        logger.error(f"Error processing BVD file: {str(e)}")
        cache.set(f"bvd_import_{batch_id}_status", {
            "status": "FAILED",
            "error": str(e)
        }, timeout=3600)
        raise

def process_row(row, tenant_id):
    """Process a single row of BVD data"""
    cleaned_data = {}

    try:
        # Handle date and time
        date_value = row.get("Date")
        time_value = row.get("Time", "00:00")
        datetime_obj = combine_date_time(date_value, time_value)
        cleaned_data["date"] = datetime_obj
        cleaned_data["time"] = datetime_obj.strftime("%H:%M")

        # Map fields
        field_mappings = {
            "Company Name": "company_name",
            "Card#": "card_number",
            "Driver Name": "driver_name",
            "Unit #": "unit",
            "Site #": "site_number",
            "Site Name": "site_name",
            "Site City": "site_city",
            "Prov/ST": "prov_st",
            "Quantity": "quantity",
            "UOM": "uom",
            "Retail PPU": "retail_ppu",
            "Billed PPU": "billed_ppu",
            "PreTax AMT": "pre_tax_amt",
            "PST": "pst",
            "GST": "gst",
            "HST": "hst",
            "QST": "qst",
            "Discount": "discount",
            "Final Amount": "final_amount",
            "Currency": "currency",
            "Odometer": "odometer",
            "Auth Code": "auth_code",
        }

        # Process each field
        for excel_col, model_field in field_mappings.items():
            if excel_col in row:
                value = row[excel_col]

                # Handle different field types
                if model_field in [
                    "quantity",
                    "retail_ppu",
                    "billed_ppu",
                    "pre_tax_amt",
                    "pst",
                    "gst",
                    "hst",
                    "qst",
                    "discount",
                    "final_amount",
                ]:
                    value = clean_numeric(value)
                elif model_field == "odometer":
                    value = clean_integer(value)
                elif model_field == "unit":
                    value = clean_unit(value)
                elif pd.isna(value):
                    value = ""
                else:
                    value = str(value).strip()

                cleaned_data[model_field] = value

        # Set default values
        cleaned_data["currency"] = cleaned_data.get("currency", "CAD")
        cleaned_data["tenant_id"] = tenant_id
        cleaned_data["status"] = AccountPayableStatus.PENDING

        # Validate quantity
        if cleaned_data.get("quantity", 0) <= 0:
            raise ValidationError("Quantity must be greater than 0")

        # Get associated truck
        truck = get_truck_from_unit(cleaned_data["unit"], tenant_id)
        cleaned_data["truck"] = truck
        cleaned_data["driver"] = truck.driver

        # Check for duplicates
        is_duplicate, duplicate_message = check_duplicates(cleaned_data)
        if is_duplicate:
            raise ValidationError(duplicate_message)

        return cleaned_data

    except ValidationError as e:
        raise ValidationError(f"Row processing error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error processing row: {str(e)}")
        raise ValidationError(f"Unexpected error: {str(e)}")

def clean_numeric(value):
    """Convert numeric values, handling various formats"""
    if pd.isna(value) or value == "":
        return 0
    try:
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").strip()
        return float(value)
    except (ValueError, TypeError):
        return 0

def clean_integer(value):
    """Convert to integer, handling various formats"""
    try:
        return int(float(value)) if pd.notna(value) else 0
    except (ValueError, TypeError):
        return 0

def clean_unit(value):
    """Clean unit number value"""
    if pd.notna(value):
        try:
            return str(int(float(value)))
        except (ValueError, TypeError):
            return "".join(filter(str.isdigit, str(value)))
    return ""

def combine_date_time(date_value, time_value):
    """Combine date and time into timezone-aware datetime"""
    try:
        # Handle date
        if isinstance(date_value, (datetime, pd.Timestamp)):
            date_part = date_value.strftime("%Y-%m-%d")
        else:
            date_obj = pd.to_datetime(date_value)
            date_part = date_obj.strftime("%Y-%m-%d")

        # Handle time
        if isinstance(time_value, str) and time_value.strip():
            try:
                time_obj = pd.to_datetime(time_value).strftime("%H:%M:%S")
            except Exception:
                time_obj = "00:00:00"
        else:
            time_obj = "00:00:00"

        # Combine and make timezone-aware
        datetime_str = f"{date_part} {time_obj}"
        naive_datetime = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")

        if settings.USE_TZ:
            timezone_name = settings.TIME_ZONE
            timezone_obj = pytz.timezone(timezone_name)
            return timezone_obj.localize(naive_datetime)
        return naive_datetime

    except Exception as e:
        raise ValidationError(f"Invalid date/time format: Date={date_value}, Time={time_value}")

def get_truck_from_unit(unit, tenant_id):
    """Get truck based on unit number"""
    try:
        return Truck.objects.get(unit=unit, tenant_id=tenant_id)
    except Truck.DoesNotExist:
        raise ValidationError(f"No truck found for unit {unit}")
    except Exception as e:
        logger.error(f"Error retrieving truck for unit {unit}: {str(e)}")
        raise

def check_duplicates(cleaned_data):
    """Check for duplicate transactions"""
    date_to_check = cleaned_data["date"]
    time_window = timedelta(minutes=5)
    tenant_id = cleaned_data["tenant_id"]

    # Check by card number and auth code
    existing = BVD.objects.filter(
        tenant_id=tenant_id,
        date__range=(date_to_check - time_window, date_to_check + time_window),
        card_number=cleaned_data.get("card_number", ""),
        auth_code=cleaned_data.get("auth_code", ""),
        final_amount=cleaned_data.get("final_amount", 0),
    ).first()

    if existing:
        return True, "Duplicate transaction found (matching card, auth code and amount)"

    # Check by unit and transaction details
    existing = BVD.objects.filter(
        tenant_id=tenant_id,
        date__range=(date_to_check - time_window, date_to_check + time_window),
        unit=cleaned_data.get("unit"),
        site_number=cleaned_data.get("site_number", ""),
        quantity=cleaned_data.get("quantity", 0),
    ).first()

    if existing:
        return True, "Duplicate transaction found (matching unit, site and quantity)"

    return False, "" 