import logging
import base64
from pathlib import Path
import os
import mimetypes
from typing import Optional
from pydantic import BaseModel, Field
from contrib.extraction.oai import client, MODELS
from PyPDF2 import PdfReader
import json

logger = logging.getLogger("django")


def determine_file_type(file_path: str) -> str:
    """Determine if the file is a PDF or an image"""
    try:
        # Get file extension and mime type
        file_ext = os.path.splitext(file_path)[1].lower()
        mime_type, _ = mimetypes.guess_type(file_path)

        if mime_type is None:
            # If mime type can't be determined, try to infer from extension
            if file_ext in [".pdf"]:
                return "pdf"
            elif file_ext in [
                ".jpg",
                ".jpeg",
                ".png",
                ".gif",
                ".bmp",
                ".tiff",
                ".webp",
            ]:
                return "image"
            else:
                logger.warning(f"Unknown file type for {file_path}")
                return "unknown"

        # Check mime type
        if mime_type.startswith("image/"):
            return "image"
        elif mime_type == "application/pdf":
            return "pdf"
        else:
            logger.warning(f"Unsupported mime type: {mime_type}")
            return "unknown"
    except Exception as e:
        logger.error(f"Error determining file type: {e}")
        return "unknown"


def encode_image(image_path: str) -> str | None:
    """Encode an image file to base64"""
    try:
        # Using Path for better cross-platform compatibility
        path = Path(image_path)
        with path.open("rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    except FileNotFoundError:
        logger.error(f"File not found: {image_path}")
        return None
    except Exception as e:
        logger.error(f"Error encoding image: {e}")
        return None


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from a PDF file"""
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n\n"
        return text
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        raise


class DriverLicenseExtraction(BaseModel):
    """
    Pydantic model for driver's license information matching Django ORM structure.
    Only fields typically found on a driver's license are required.
    """
    # Required fields (typically always present on a license)
    name: str = Field(..., description="Full name as shown on license")
    license_number: str = Field(..., description="Driver's license number")
    date_of_birth: str = Field(..., description="Date of birth in ISO format (YYYY-MM-DD)")
    expiry_date: str = Field(..., description="License expiration date in ISO format (YYYY-MM-DD)")
    
    # Optional fields (may not be present or readable)
    issued_date: Optional[str] = Field(None, description="License issue date in ISO format (YYYY-MM-DD)")
    gender: Optional[str] = Field(None, description="Gender/Sex as shown on license")
    address: Optional[str] = Field(None, description="Full street address")
    country: Optional[str] = Field(None, description="Country of issuance")
    province: Optional[str] = Field(None, description="Province (for Canadian licenses)")
    state: Optional[str] = Field(None, description="State (for US licenses)")

    # Japanese-specific fields
    license_type: Optional[str] = Field(None, description="Type of license (e.g., 普通車)")
    conditions: Optional[str] = Field(None, description="License conditions or restrictions (e.g., AT車に限る)")
    license_class: Optional[str] = Field(None, description="License class or grade (e.g., 優良)")
    public_safety_commission: Optional[str] = Field(None, description="Issuing public safety commission (e.g., 公安委員会)")

    class Config:
        extra = "forbid"


def extract_license_info(file_path: str) -> DriverLicenseExtraction:
    """
    Extract driver's license information from an image or PDF and return structured data.

    Args:
        file_path (str): Path to the license image or PDF

    Returns:
        DriverLicenseExtraction: Structured license information
    """
    # Check if file exists
    if not os.path.exists(file_path):
        logger.error(f"File does not exist: {file_path}")
        raise FileNotFoundError(f"Could not find file at {file_path}")

    # Determine file type
    file_type = determine_file_type(file_path)
    logger.info(f"Processing {file_type} file: {file_path}")

    try:
        if file_type == "pdf":
            # Extract text from PDF first
            extracted_text = extract_text_from_pdf(file_path)
            if not extracted_text.strip():
                raise ValueError("No text could be extracted from the PDF")

            # Process the extracted text
            response = client.chat.completions.create(
                model=MODELS.GPT4o_16k.value,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": "Extract driver's license information into a structured JSON format. Convert dates to ISO format (YYYY-MM-DD). Return the data as a JSON object with the following fields: name, license_number, date_of_birth, issued_date, expiry_date, gender, address, country, province, state.",
                    },
                    {
                        "role": "user",
                        "content": f"Extract license information from this text and return as JSON: {extracted_text}",
                    },
                ],
                response_format={"type": "json_object"},
                max_tokens=500,
            )
            
            # Parse the JSON response into our Pydantic model
            license_data = json.loads(response.choices[0].message.content)
            return DriverLicenseExtraction(**license_data)

        elif file_type == "image":
            # Process image
            base64_image = encode_image(file_path)
            if not base64_image:
                raise FileNotFoundError(f"Could not load image from {file_path}")

            # Extract text from image using GPT-4 Vision
            text_response = client.chat.completions.create(
                model=MODELS.GPT4o_16k.value,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at reading driver's licenses. Extract all text from the image, including names, numbers, dates, and addresses. If you can't read the image clearly, explain what parts are unclear.",
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Read this driver's license image and extract all text you can see. Include every detail visible.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                },
                            },
                        ],
                    }
                ],
                max_tokens=500,
            )

            extracted_text = text_response.choices[0].message.content
            if "error" in extracted_text.lower() or "no text" in extracted_text.lower():
                logger.error(f"GPT-4 Vision failed to read image: {extracted_text}")
                raise ValueError(f"Could not read text from image: {extracted_text}")

            # Process the extracted text into structured format
            response = client.chat.completions.create(
                model=MODELS.GPT4o_16k.value,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert at parsing driver's license information.
Extract the information into a structured JSON format. Convert all dates to ISO format (YYYY-MM-DD).
If a field is not found, use an empty string or null as appropriate.
Return a JSON object with these fields: name, license_number, date_of_birth, issued_date, expiry_date, gender, address, country, province, state."""
                    },
                    {
                        "role": "user",
                        "content": f"Parse this driver's license text into JSON format. If any field is unclear or missing, use an empty string: {extracted_text}",
                    },
                ],
                response_format={"type": "json_object"},
                max_tokens=500,
            )
            
            # Parse the JSON response into our Pydantic model
            try:
                license_data = json.loads(response.choices[0].message.content)
                return DriverLicenseExtraction(**license_data)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {response.choices[0].message.content}")
                raise ValueError(f"Failed to parse license data: {str(e)}")
            except Exception as e:
                logger.error(f"Failed to create DriverLicenseExtraction: {str(e)}")
                raise ValueError(f"Invalid license data format: {str(e)}")
        else:
            # Unsupported file type
            raise ValueError(f"Unsupported file type: {file_type}")

    except Exception as e:
        logger.error(f"Error processing license file: {str(e)}", exc_info=True)
        raise
