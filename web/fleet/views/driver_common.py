from django import forms
from django.views import View
from django.shortcuts import render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
import os
import secrets
import logging
from pathlib import Path
from django.conf import settings
from contrib.aws import s3_utils
from fleet.utils import extract_driver_license_info, map_driver_data, ensure_tmp_directories
from fleet.models import DriverLicense, Driver
from django.core.exceptions import ValidationError
from uuid import UUID
from contrib.extraction.oai import MODELS

logger = logging.getLogger("django")


class DriverLicenseUploadForm(forms.Form):
    license_file = forms.FileField(
        label="Driver's License File",
        widget=forms.FileInput(
            attrs={"class": "form-control", "accept": "image/*,.pdf"}
        ),
        help_text="Upload driver's license image or PDF",
    )


class DriverLicenseUploadView(LoginRequiredMixin, View):
    template_name = "driver/upload_license.html"
    form_class = DriverLicenseUploadForm

    def get(self, request):
        form = self.form_class()
        return render(request, self.template_name, {"form": form})

    def handle_uploaded_file(self, file, user):
        filename = f"{secrets.token_urlsafe(6)}_{file.name}"

        file_dir = os.path.join(
            settings.MEDIA_ROOT,
            settings.ENV,
            "driver_licenses",
            str(user.profile.tenant.id),
        )
        filepath = os.path.join(file_dir, filename)

        # Create directory if it doesn't exist
        Path(file_dir).mkdir(parents=True, exist_ok=True)

        with open(filepath, "wb+") as destination:
            for chunk in file.chunks():
                destination.write(chunk)

        return filepath, filename, file.content_type, file_dir

    def post(self, request):
        try:
            form = self.form_class(request.POST, request.FILES)
            if not form.is_valid():
                messages.error(request, "Invalid form submission")
                return render(request, self.template_name, {"form": form})

            file = request.FILES["license_file"]
            tenant = request.user.profile.tenant

            # Handle file upload
            filepath, filename, content_type, file_dir = self.handle_uploaded_file(
                file, request.user
            )
            logger.info(f"File saved locally at: {filepath}")

            # Upload to S3
            s3_key = f"{settings.ENV}/{tenant.id}/driver_licenses/{filename}"
            logger.info(f"Uploading to S3 with key: {s3_key}")
            
            s3_upload_success = s3_utils.upload_file(
                filepath,
                s3_key,
            )
            logger.info(f"S3 upload success: {s3_upload_success}")

            if not s3_upload_success:
                messages.error(request, "Failed to upload file to S3")
                raise ValidationError("Failed to upload file to S3")

            try:
                # Process the license file synchronously
                logger.info(f"Starting license processing for file: {filename}")
                
                # Create tmp directory if it doesn't exist
                tmp_dir = os.path.join(settings.BASE_DIR, "tmp", "documents")
                os.makedirs(tmp_dir, exist_ok=True)
                
                # Download from S3 to process
                local_path = os.path.join(tmp_dir, f"{secrets.token_urlsafe(6)}_{filename}")
                logger.info(f"Downloading file from S3: {s3_key}")
                s3_download_success = s3_utils.download_file(s3_key, local_path)
                logger.info(f"S3 download success: {s3_download_success}")
                
                if not s3_download_success:
                    raise Exception(f"Failed to download file from S3: {s3_key}")

                # Extract license information
                logger.info("Starting license information extraction")
                license_info, token_usage = extract_driver_license_info(local_path)
                logger.info(f"License info extracted with {token_usage.get('total_tokens', 0)} tokens used")

                # Create driver license record
                driver_license = DriverLicense.objects.create(
                    name=license_info.name,
                    license_number=license_info.license_number,
                    date_of_birth=license_info.date_of_birth,
                    issued_date=license_info.issued_date,
                    expiry_date=license_info.expiry_date,
                    gender=license_info.gender,
                    address=license_info.address,
                    country=license_info.country,
                    province=license_info.province,
                    state=license_info.state,
                    completion_tokens=token_usage.get("completion_tokens", 0),
                    prompt_tokens=token_usage.get("prompt_tokens", 0),
                    total_tokens=token_usage.get("total_tokens", 0),
                    llm_model_name=MODELS.GPT4o_16k.value,
                    uploaded_file_name=filename,
                    file_save_path=s3_key,
                    tenant=tenant,
                )

                # Map and create/update driver record
                driver = map_driver_data(license_info, driver_license, tenant)
                
                logger.info(
                    f"Successfully processed license {driver_license.id} for driver {driver.id}. "
                    f"Tokens used: {token_usage.get('total_tokens', 0)}"
                )

                messages.success(request, "Driver's license uploaded and processed successfully.")
                
                # Cleanup temporary files
                try:
                    os.remove(local_path)
                    os.remove(filepath)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temporary files: {str(e)}")

                return redirect("fleet:driver-license-detail", pk=driver_license.pk)

            except Exception as e:
                logger.error(f"Error processing license: {str(e)}", exc_info=True)
                messages.error(request, f"Failed to process license: {str(e)}")
                return render(request, self.template_name, {"form": form})

        except ValidationError as e:
            messages.error(request, str(e))
            return render(request, self.template_name, {"form": form})
        except Exception as e:
            logger.error(f"Error processing upload: {str(e)}", exc_info=True)
            messages.error(request, "An unexpected error occurred")
            return render(request, self.template_name, {"form": form})
