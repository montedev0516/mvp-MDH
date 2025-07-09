from django import forms
from django.conf import settings
import os
import magic
import logging

logger = logging.getLogger(__name__)

class FileUploadForm(forms.Form):
    """Form for handling file uploads in the dispatch system."""
    
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_MIME_TYPES = ['application/pdf']
    ALLOWED_EXTENSIONS = ['.pdf']
    
    files = forms.FileField(
        widget=forms.ClearableFileInput(
            attrs={
                "multiple": False,
                "accept": ".pdf",
                "class": "form-control"
            }
        ),
        help_text="Only PDF files are allowed. Maximum file size: 10MB",
    )

    def clean_files(self):
        """Validate uploaded files for type, size, and content."""
        files = self.files.getlist("files")
        
        for file in files:
            # Check file size
            if file.size > self.MAX_FILE_SIZE:
                raise forms.ValidationError(
                    f"File size cannot exceed {self.MAX_FILE_SIZE / (1024 * 1024)}MB. "
                    f"Current file size: {file.size / (1024 * 1024):.2f}MB"
                )

            # Check file extension
            file_ext = os.path.splitext(file.name)[1].lower()
            if file_ext not in self.ALLOWED_EXTENSIONS:
                raise forms.ValidationError(
                    f"Invalid file type. Allowed types: {', '.join(self.ALLOWED_EXTENSIONS)}"
                )

            # Check MIME type
            try:
                # Read first 2048 bytes for MIME detection
                file_content = file.read(2048)
                mime_type = magic.from_buffer(file_content, mime=True)
                file.seek(0)  # Reset file pointer
                
                if mime_type not in self.ALLOWED_MIME_TYPES:
                    raise forms.ValidationError(
                        f"Invalid file content. File appears to be {mime_type}"
                    )
            except Exception as e:
                logger.error(f"💥Error checking file type: {str(e)}")
                raise forms.ValidationError("Error validating file type")

        return files

    def get_upload_path(self, tenant_id, filename):
        """Generate the upload path for the file."""
        return os.path.join(
            settings.MEDIA_ROOT,
            settings.ENV,
            "order_files",
            str(tenant_id),
            filename
        )
