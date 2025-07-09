import os
import logging
from django.core.exceptions import ValidationError

logger = logging.getLogger("django")


def calculate_file_size_mb(file_or_path) -> float:
    """
    Calculate file size in megabytes with precision for both file objects and paths

    Args:
        file_or_path: Either a file object (InMemoryUploadedFile) or a file path (str)

    Returns:
        float: File size in megabytes with 3 decimal precision
    """
    try:
        if isinstance(file_or_path, str):
            # If it's a file path
            size_in_bytes = os.path.getsize(file_or_path)
        else:
            # If it's a file object
            size_in_bytes = file_or_path.size

        return round(size_in_bytes / (1024 * 1024), 3)
    except Exception as e:
        logger.error(f"Error calculating file size: {str(e)}", exc_info=True)
        raise ValidationError(f"Error calculating file size: {str(e)}")
