import uuid
import logging
from datetime import datetime, timedelta
from decimal import Decimal
import pandas as pd
import pytz
from django.conf import settings
from django.db.models import Q
from django.db import transaction
from django.core.exceptions import ValidationError
from django.core.cache import cache
from models.models import (
    Currency,
    ExchangeRate,
)
from expense.models import BVD, Payout, PayoutStatus, AccountPayableStatus
from fleet.models import Truck, Driver
from dispatch.models import DriverTruckAssignment, AssignmentStatus
import re
import decimal
from django.utils import timezone

logger = logging.getLogger("django")

BVD_CURRENCY_MAP = {"CN": "CAD", "US": "USD"}


def normalize_currency(currency: str) -> str:
    """
    Normalize currency codes to match Currency enum values.
    """
    return BVD_CURRENCY_MAP.get(currency, currency)


def get_exchange_rate(from_currency: str, to_currency: str) -> Decimal:
    """
    Get exchange rate for currency conversion.
    Returns 1 if same currency, otherwise fetches from ExchangeRate model.
    """
    if from_currency == to_currency:
        return Decimal("1.0")

    try:
        rate = ExchangeRate.objects.get(
            from_currency=from_currency, to_currency=to_currency, is_active=True
        ).rate
        return Decimal(str(rate))
    except ExchangeRate.DoesNotExist:
        logger.error(f"Exchange rate not found for {from_currency} to {to_currency}")
        return Decimal("1.0")


class BVDFileProcessor:
    """Process BVD files without using Celery"""

    def __init__(self, file_obj, tenant_id, batch_id):
        self.file_obj = file_obj
        self.tenant_id = tenant_id
        self.batch_id = batch_id
        self.total_records = 0
        self.success_count = 0
        self.error_count = 0
        self.skipped_count = 0
        self.error_details = []
        self.skipped_details = []
        logger.info(f"🐱‍🏍🐱‍🏍🐱‍🏍Initializing BVD file processor with tenant_id: {tenant_id}, batch_id: {batch_id}")

    def process_file(self):
        """Process the BVD file and track progress"""
        try:
            # Initialize progress tracking
            self._update_progress(0, "PROCESSING")

            # Read file with proper error handling
            try:
                file_extension = self.file_obj.name.split(".")[-1].lower()
                if file_extension == "csv":
                    df = pd.read_csv(self.file_obj, encoding='utf-8')
                else:
                    df = pd.read_excel(self.file_obj)
            except UnicodeDecodeError:
                # Try with different encodings
                try:
                    self.file_obj.seek(0)
                    df = pd.read_csv(self.file_obj, encoding='latin1')
                except Exception:
                    try:
                        self.file_obj.seek(0)
                        df = pd.read_csv(self.file_obj, encoding='cp1252')
                    except Exception:
                        raise ValidationError("Unable to read file. Please ensure it's saved as UTF-8 encoding.")
            except pd.errors.EmptyDataError:
                raise ValidationError("The file appears to be empty or contains no data.")
            except pd.errors.ParserError:
                raise ValidationError("Unable to parse the file. Please check the file format.")
            except Exception as e:
                logger.error(f"Error reading file: {str(e)}")
                raise ValidationError("Unable to read the file. Please check the file format and try again.")

            # Validate file has data
            if df.empty:
                raise ValidationError("The file contains no data rows.")

            # Clean column names
            df.columns = df.columns.str.strip()

            # Validate required columns
            required_columns = ['Date', 'Unit #', 'Final Amount']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                raise ValidationError(f"Missing required columns: {', '.join(missing_columns)}")

            # Log column names and first few rows
            logger.info(f"🔍 CSV Columns: {list(df.columns)}")
            logger.info("First few rows of data:")
            for idx, row in df.head().iterrows():
                logger.info(f"Row {idx + 1}:")
                for col in df.columns:
                    logger.info(f"   {col}: {row[col]}")

            # Update total records
            self.total_records = len(df)
            self._update_progress(0, "PROCESSING")
            logger.info(f"Total records to process: {self.total_records}")

            # Track different types of skipped rows
            skipped_units = {
                'missing_truck': set(),
                'no_assignment': set(),        # No assignment covering the transaction date
                'cancelled_assignment': set(), # Assignment was cancelled
                'other': set()
            }

            # Process in batches of 100
            batch_size = 100
            processed_count = 0
            
            for start_idx in range(0, len(df), batch_size):
                # Check if import has been cancelled
                try:
                    status = cache.get(f"bvd_import_{self.batch_id}_status")
                    if status and status.get('status') == 'CANCELLED':
                        logger.info("🛑 Import cancelled by user")
                        return {
                            "total": self.total_records,
                            "processed": processed_count,
                            "success": self.success_count,
                            "errors": self.error_count,
                            "skipped": self.skipped_count,
                            "error_details": self.error_details,
                            "skipped_details": self.skipped_details,
                            "skipped_units": {k: sorted(list(v)) for k, v in skipped_units.items()},
                            "status": "CANCELLED"
                        }
                except Exception:
                    # If cache check fails, continue processing
                    pass

                end_idx = min(start_idx + batch_size, len(df))
                batch_df = df.iloc[start_idx:end_idx]
                logger.info(f"Processing batch {start_idx + 1} to {end_idx}")

                for row_idx, row in batch_df.iterrows():
                    processed_count += 1
                    try:
                        # Log raw row data
                        logger.info(f"🔄 Processing row {row_idx + 1}:")
                        logger.info("📝 Raw data:")
                        for col in df.columns:
                            logger.info(f"   {col}: {row[col]}")

                        cleaned_data = self._process_row(row)
                        
                        # Skip if row should be ignored (e.g., missing truck)
                        if cleaned_data is None:
                            unit = self._clean_unit(row.get("Unit #", ""))
                            skipped_units['missing_truck'].add(unit)
                            self.skipped_count += 1
                            self.skipped_details.append(f"Row {row_idx + 1}: Missing truck for unit {unit}")
                            logger.warning(f"⚠️ Row {row_idx + 1} skipped - Missing truck for unit {unit}")
                            continue

                        # Log cleaned data
                        logger.info("✨ Cleaned data:")
                        for key, value in cleaned_data.items():
                            logger.info(f"   {key}: {value}")

                        # Create BVD record with error handling
                        try:
                            bvd = BVD.objects.create(**cleaned_data)
                            logger.info(f"✅ Created BVD record with ID: {bvd.id}")
                            self.success_count += 1
                        except Exception as e:
                            logger.error(f"Database error creating BVD record: {str(e)}")
                            self.error_count += 1
                            self.error_details.append(f"Row {row_idx + 1}: Database error - {str(e)}")
                        
                    except ValidationError as e:
                        # Categorize different skip reasons
                        unit = self._clean_unit(row.get("Unit #", ""))
                        error_msg = str(e)
                        
                        if "No driver assignment found" in error_msg:
                            skipped_units['no_assignment'].add(unit)
                            self.skipped_count += 1
                            self.skipped_details.append(f"Row {row_idx + 1}: No assignment for unit {unit}")
                            logger.warning(f"⚠️ Row {row_idx + 1} skipped - No assignment for unit {unit}")
                        elif "was cancelled" in error_msg:
                            skipped_units['cancelled_assignment'].add(unit)
                            self.skipped_count += 1
                            self.skipped_details.append(f"Row {row_idx + 1}: Assignment was cancelled for unit {unit}")
                            logger.warning(f"⚠️ Row {row_idx + 1} skipped - Assignment was cancelled for unit {unit}")
                        else:
                            # Actual errors that should be reported (duplicates, validation errors, etc.)
                            self.error_count += 1
                            self.error_details.append(f"Row {row_idx + 1}: {error_msg}")
                            logger.error(f"❌ Row {row_idx + 1} error: {error_msg}")
                        
                    except Exception as e:
                        self.error_count += 1
                        error_msg = f"Processing error: {str(e)}"
                        self.error_details.append(f"Row {row_idx + 1}: {error_msg}")
                        logger.error(f"💥 Row {row_idx + 1} unexpected error: {error_msg}")

                # Update progress after each batch
                try:
                    self._update_progress(processed_count)
                except Exception:
                    # If progress update fails, continue processing
                    pass

            # Log summary of skipped units
            total_skipped = sum(len(units) for units in skipped_units.values())
            if total_skipped > 0:
                logger.warning(f"⚠️ Summary of skipped rows:")
                logger.warning(f"   Missing trucks: {len(skipped_units['missing_truck'])} units: {sorted(list(skipped_units['missing_truck']))}")
                logger.warning(f"   No assignments: {len(skipped_units['no_assignment'])} units: {sorted(list(skipped_units['no_assignment']))}")
                logger.warning(f"   Cancelled assignments: {len(skipped_units['cancelled_assignment'])} units: {sorted(list(skipped_units['cancelled_assignment']))}")
                logger.warning(f"   Other reasons: {len(skipped_units['other'])} units: {sorted(list(skipped_units['other']))}")

            # Determine final status
            if self.success_count == 0 and self.error_count == 0 and self.skipped_count > 0:
                status = "COMPLETED_WITH_SKIPS"
            elif self.error_count > 0:
                status = "COMPLETED_WITH_ERRORS"
            else:
                status = "COMPLETED"
                
            try:
                self._update_progress(self.total_records, status)
            except Exception:
                # If final progress update fails, continue
                pass

            logger.info(f"Import completed - Success: {self.success_count}, Errors: {self.error_count}, Skipped: {self.skipped_count}")
            
            return {
                "total": self.total_records,
                "processed": processed_count,
                "success": self.success_count,
                "errors": self.error_count,
                "skipped": self.skipped_count,
                "error_details": self.error_details,
                "skipped_details": self.skipped_details,
                "skipped_units": {k: sorted(list(v)) for k, v in skipped_units.items()}
            }

        except ValidationError as e:
            logger.error(f"🚨 File validation error: {str(e)}")
            self._update_progress(
                self.total_records,
                "ERROR",
                str(e)
            )
            raise e
        except Exception as e:
            logger.error(f"🚨 File processing error: {str(e)}")
            self._update_progress(
                self.total_records,
                "ERROR",
                f"File processing error: {str(e)}"
            )
            raise ValidationError(f"File processing failed: {str(e)}")

    def _update_progress(self, processed_count, status="PROCESSING", error=None):
        """Update progress in cache"""
        progress_data = {
            "status": status,
            "total": self.total_records,
            "processed": processed_count,
            "success": self.success_count,
            "errors": self.error_count,
            "skipped": self.skipped_count,
            "error_details": self.error_details[-5:],  # Keep last 5 errors
            "skipped_details": self.skipped_details[-5:]  # Keep last 5 skipped
        }
        if error:
            progress_data["error"] = error
            
        cache.set(f"bvd_import_{self.batch_id}_status", progress_data, timeout=3600)

    def _process_row(self, row):
        """Process a single row from the BVD file with comprehensive error handling"""
        try:
            # Map fields with error handling
            field_mappings = {
                "Company Name": "company_name",
                "Card#": "card_number",
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
                "Final Amount": "amount",
                "Currency": "currency",
                "Date": "date",
                "Site #": "site_number",
                "Auth Code": "auth_code",
                "Sub Total": "sub_total",
                "Vehicle #": "vehicle_number",
                "Account": "account",
                "Status": "status",
                "Odometer": "odometer"
            }

            # Initialize cleaned data
            cleaned_data = {"tenant_id": self.tenant_id}

            # Map and clean each field
            for csv_field, db_field in field_mappings.items():
                if csv_field in row and pd.notna(row[csv_field]):
                    try:
                        cleaned_data[db_field] = self._clean_field_value(row[csv_field], db_field)
                    except Exception as e:
                        logger.warning(f"Error cleaning field {csv_field}: {str(e)}")
                        # Continue processing, just skip problematic fields

            # Required field validations
            required_fields = ["date", "unit", "amount"]
            missing_fields = [field for field in required_fields if field not in cleaned_data or not cleaned_data[field]]
            if missing_fields:
                raise ValidationError(f"Missing required fields: {', '.join(missing_fields)}")

            # Data type conversions with error handling
            numeric_fields = ["quantity", "retail_ppu", "billed_ppu", "pre_tax_amt", "pst", "gst", "hst", "qst", "discount", "amount"]
            for field in numeric_fields:
                if field in cleaned_data and cleaned_data[field] is not None:
                    try:
                        cleaned_data[field] = self._convert_to_decimal(cleaned_data[field])
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Error converting {field} to decimal: {str(e)}")
                        cleaned_data[field] = Decimal('0.00')

            # Date field handling
            if "date" in cleaned_data:
                try:
                    cleaned_data["date"] = self._parse_date(cleaned_data["date"])
                except Exception as e:
                    logger.error(f"Error parsing date: {str(e)}")
                    raise ValidationError(f"Invalid date format: {cleaned_data.get('date', 'N/A')}")

            # Truck and Driver lookup with improved error handling
            unit = self._clean_unit(cleaned_data.get("unit", ""))
            if not unit:
                raise ValidationError("Missing or invalid unit number")

            try:
                truck = Truck.objects.get(unit=unit, tenant_id=self.tenant_id)
                cleaned_data["truck"] = truck
            except Truck.DoesNotExist:
                logger.warning(f"⚠️ Skipping row - Truck with unit {unit} not found in database")
                return None  # Skip this row instead of raising an error
            except Exception as e:
                logger.error(f"Error looking up truck with unit {unit}: {str(e)}")
                raise ValidationError(f"Error processing truck unit {unit}")

            # Driver assignment lookup
            transaction_date = cleaned_data["date"]
            try:
                assignment = DriverTruckAssignment.objects.filter(
                    truck=truck,
                    start_date__lte=transaction_date,
                    end_date__gte=transaction_date,
                    tenant_id=self.tenant_id
                ).exclude(
                    status=AssignmentStatus.CANCELLED
                ).first()

                if not assignment:
                    raise ValidationError(f"No driver assignment found for truck {unit} on {transaction_date.date()}")

                if assignment.status == AssignmentStatus.CANCELLED:
                    raise ValidationError(f"Driver assignment for truck {unit} was cancelled")

                cleaned_data["driver"] = assignment.driver
                logger.info(f"✅ Found driver assignment: {assignment.driver} for truck {unit}")

            except DriverTruckAssignment.DoesNotExist:
                raise ValidationError(f"No driver assignment found for truck {unit} on {transaction_date.date()}")
            except Exception as e:
                logger.error(f"Error looking up driver assignment: {str(e)}")
                raise ValidationError(f"Error processing driver assignment for truck {unit}")

            # Set default currency if not provided
            if "currency" not in cleaned_data or not cleaned_data["currency"]:
                cleaned_data["currency"] = "CAD"

            # Set default status
            if "status" not in cleaned_data or not cleaned_data["status"]:
                cleaned_data["status"] = AccountPayableStatus.PENDING

            # Validate amount
            if cleaned_data.get("amount", 0) <= 0:
                logger.warning(f"Invalid amount for unit {unit}: {cleaned_data.get('amount', 'N/A')}")

            # Check for duplicates
            try:
                if self._is_duplicate(cleaned_data):
                    raise ValidationError(f"Duplicate record found for truck {unit} on {transaction_date}")
            except Exception as e:
                logger.warning(f"Error checking for duplicates: {str(e)}")
                # Continue processing even if duplicate check fails

            logger.info(f"✅ Successfully processed row for truck {unit}")
            return cleaned_data

        except ValidationError as e:
            # Re-raise validation errors as they are expected
            raise e
        except Exception as e:
            logger.error(f"Unexpected error processing row: {str(e)}")
            unit = self._clean_unit(row.get("Unit #", "Unknown"))
            raise ValidationError(f"Processing error for unit {unit}: {str(e)}")

    def _clean_field_value(self, value, field_name):
        """Clean individual field values based on field type"""
        if pd.isna(value) or value == "":
            return None
            
        if field_name in ["quantity", "retail_ppu", "billed_ppu", "pre_tax_amt", "pst", "gst", "hst", "qst", "discount", "amount"]:
            return self._convert_to_decimal(value)
        elif field_name == "unit":
            return self._clean_unit(value)
        elif field_name == "date":
            return value  # Will be processed separately
        elif field_name == "odometer":
            return self._clean_integer(value)
        else:
            return str(value).strip()
    
    def _convert_to_decimal(self, value):
        """Convert value to Decimal with proper error handling"""
        if value is None or value == "" or pd.isna(value):
            return Decimal('0.00')
            
        try:
            # Handle string values with currency symbols and commas
            if isinstance(value, str):
                # Remove currency symbols and commas
                cleaned = re.sub(r'[,$%]', '', value.strip())
                if not cleaned:
                    return Decimal('0.00')
                value = cleaned
                
            return Decimal(str(value))
        except (ValueError, TypeError, decimal.InvalidOperation):
            logger.warning(f"Could not convert '{value}' to decimal, using 0.00")
            return Decimal('0.00')
    
    def _parse_date(self, date_value):
        """Parse date value with multiple format support"""
        if pd.isna(date_value) or date_value == "":
            raise ValueError("Date value is empty")
            
        # If already a datetime object, return it
        if isinstance(date_value, datetime):
            return date_value
            
        # Convert to string for parsing
        date_str = str(date_value).strip()
        
        # Common date formats to try
        date_formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M",
            "%m/%d/%Y",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y/%m/%d",
        ]
        
        for fmt in date_formats:
            try:
                parsed_date = datetime.strptime(date_str, fmt)
                # Ensure timezone aware
                if parsed_date.tzinfo is None:
                    parsed_date = timezone.make_aware(parsed_date)
                return parsed_date
            except ValueError:
                continue
                
        # If no format worked, try pandas to_datetime as last resort
        try:
            parsed_date = pd.to_datetime(date_str)
            if isinstance(parsed_date, pd.Timestamp):
                parsed_date = parsed_date.to_pydatetime()
            if parsed_date.tzinfo is None:
                parsed_date = timezone.make_aware(parsed_date)
            return parsed_date
        except Exception:
            raise ValueError(f"Unable to parse date: {date_str}")
    
    def _is_duplicate(self, cleaned_data):
        """Check if this record already exists to prevent duplicates"""
        try:
            existing = BVD.objects.filter(
                truck=cleaned_data["truck"],
                driver=cleaned_data["driver"],
                date=cleaned_data["date"],
                amount=cleaned_data["amount"],
                tenant_id=self.tenant_id
            ).exists()
            return existing
        except Exception as e:
            logger.warning(f"Error checking for duplicates: {str(e)}")
            return False  # If check fails, allow the record

    def _clean_numeric(self, value):
        """Convert numeric values, handling various formats"""
        if pd.isna(value) or value == "":
            return 0
        try:
            if isinstance(value, str):
                value = value.replace("$", "").replace(",", "").strip()
            return float(value)
        except (ValueError, TypeError):
            return 0

    def _clean_integer(self, value):
        """Convert to integer, handling various formats"""
        try:
            return int(float(value)) if pd.notna(value) else 0
        except (ValueError, TypeError):
            return 0

    def _clean_unit(self, value):
        """Clean unit number value"""
        if pd.notna(value):
            try:
                return str(int(float(value)))
            except (ValueError, TypeError):
                return "".join(filter(str.isdigit, str(value)))
        return ""

    def _combine_date_time(self, date_value, time_value):
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

    def _check_duplicates(self, cleaned_data):
        """Check for duplicate transactions"""
        date_to_check = cleaned_data["date"]
        time_window = timedelta(minutes=5)

        # Check by card number and auth code
        existing = BVD.objects.filter(
            tenant_id=self.tenant_id,
            date__range=(date_to_check - time_window, date_to_check + time_window),
            card_number=cleaned_data.get("card_number", ""),
            auth_code=cleaned_data.get("auth_code", ""),
            amount=cleaned_data.get("amount", 0),
        ).first()

        if existing:
            return True, "Duplicate transaction found (matching card, auth code and amount)"

        # Check by unit and transaction details
        existing = BVD.objects.filter(
            tenant_id=self.tenant_id,
            date__range=(date_to_check - time_window, date_to_check + time_window),
            unit=cleaned_data.get("unit"),
            site_number=cleaned_data.get("site_number", ""),
            quantity=cleaned_data.get("quantity", 0),
        ).first()

        if existing:
            return True, "Duplicate transaction found (matching unit, site and quantity)"

        return False, ""


def calculate_final_amount(payout, target_currency, exchange_rate):
    """
    Calculate final payout amount in target currency
    
    Args:
        payout: Payout object with cad_payout and usd_payout fields
        target_currency: 'CAD' or 'USD' 
        exchange_rate: Exchange rate (CAD/USD)
    
    Returns:
        Decimal: Final amount in target currency
    """
    from decimal import Decimal, ROUND_HALF_UP
    
    # Round exchange rate to 2 decimal places
    exchange_rate = exchange_rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    if target_currency == "CAD":
        # Convert USD to CAD and add to CAD amount
        usd_in_cad = payout.usd_payout * exchange_rate
        final_amount = payout.cad_payout + usd_in_cad
    elif target_currency == "USD":
        # Convert CAD to USD and add to USD amount
        cad_in_usd = payout.cad_payout / exchange_rate
        final_amount = payout.usd_payout + cad_in_usd
    else:
        raise ValueError(f"Unsupported currency: {target_currency}")
    
    return final_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def aggregate_bvd_expenses_for_payout(driver, tenant, from_date, to_date):
    """
    Aggregate BVD expenses for a driver within a date range
    
    Args:
        driver: Driver instance
        tenant: Tenant instance  
        from_date: Start date
        to_date: End date
        
    Returns:
        dict: {'cad_total': Decimal, 'usd_total': Decimal, 'bvd_records': QuerySet}
    """
    from decimal import Decimal
    from django.db.models import Sum, Q
    
    # Get BVD records for the driver in the date range
    bvd_records = BVD.objects.filter(
        driver=driver,
        tenant=tenant,
        date__gte=from_date,
        date__lte=to_date,
        is_active=True,
        status=AccountPayableStatus.PENDING  # Only include pending expenses
    )
    
    # Aggregate by currency
    cad_total = bvd_records.filter(currency='CAD').aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    
    usd_total = bvd_records.filter(currency='USD').aggregate(
        total=Sum('amount')  
    )['total'] or Decimal('0.00')
    
    return {
        'cad_total': cad_total,
        'usd_total': usd_total, 
        'bvd_records': bvd_records
    }


def create_driver_payout(driver, tenant, from_date, to_date, exchange_rate=None):
    """
    Create a payout record for a driver for a specific period
    
    Args:
        driver: Driver instance
        tenant: Tenant instance
        from_date: Start date
        to_date: End date
        exchange_rate: Exchange rate CAD/USD (optional)
        
    Returns:
        Payout: Created payout instance
    """
    from decimal import Decimal
    from expense.models import Payout
    from models.models import ExchangeRate
    
    # Get or calculate exchange rate
    if not exchange_rate:
        try:
            # Try to get exchange rate for the period
            exchange_rate_obj = ExchangeRate.objects.filter(
                from_currency='USD',
                to_currency='CAD',
                date__lte=to_date
            ).order_by('-date').first()
            
            if exchange_rate_obj:
                exchange_rate = exchange_rate_obj.rate
            else:
                exchange_rate = Decimal('1.33')  # Default fallback
        except:
            exchange_rate = Decimal('1.33')  # Default fallback
    
    # Aggregate BVD expenses
    bvd_data = aggregate_bvd_expenses_for_payout(driver, tenant, from_date, to_date)
    
    # Create payout record
    payout = Payout.objects.create(
        driver=driver,
        tenant=tenant,
        from_date=from_date,
        to_date=to_date,
        cad_expenses=bvd_data['cad_total'],
        usd_expenses=bvd_data['usd_total'],
        exchange_rate=exchange_rate,
        status=PayoutStatus.DRAFT
    )
    
    # Associate BVD records with the payout
    payout.bvd_expenses.set(bvd_data['bvd_records'])
    
    # Calculate final amounts
    payout.final_cad_amount = calculate_final_amount(payout, 'CAD', exchange_rate)
    payout.final_usd_amount = calculate_final_amount(payout, 'USD', exchange_rate)
    payout.save()
    
    return payout
