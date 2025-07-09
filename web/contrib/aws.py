import logging
import boto3
from pathlib import Path
from botocore.exceptions import ClientError
from typing import Union, BinaryIO, Optional
from django.conf import settings
import os

logger = logging.getLogger("django")


class S3Utils:
    def __init__(
        self,
        bucket_name: str,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        region_name: Optional[str] = None,
    ):
        """
        Initialize S3 utility with credentials and bucket name.
        If credentials are not provided, boto3 will look for them in the standard locations
        (environment variables, AWS credentials file, IAM role)
        """
        self.bucket_name = bucket_name
        try:
            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                region_name=region_name,
            )
            # Test connection
            self.s3_client.head_bucket(Bucket=bucket_name)
            logger.info(f"💘Successfully connected to S3 bucket: {bucket_name}")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_msg = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"🔥Failed to initialize S3 client. Error code: {error_code}, Message: {error_msg}")
            if error_code == "404":
                logger.error(f"Bucket '{bucket_name}' does not exist")
            elif error_code == "403":
                logger.error(f"No permission to access bucket '{bucket_name}'")
            raise

    def upload_file(
        self, file_path: Union[str, Path], s3_key: str, extra_args: dict = None
    ) -> bool:
        """
        Upload a file to S3 bucket.

        Args:
            file_path: Local path to the file
            s3_key: Destination path in S3
            extra_args: Additional arguments like ContentType, ACL, etc.

        Returns:
            bool: True if upload was successful, False otherwise
        """
        try:
            file_path = str(file_path)
            extra_args = extra_args or {}

            # Check if file exists
            if not Path(file_path).exists():
                logger.error(f"File does not exist: {file_path}")
                return False

            # Check if file is readable
            if not os.access(file_path, os.R_OK):
                logger.error(f"File is not readable: {file_path}")
                return False

            self.s3_client.upload_file(
                file_path, self.bucket_name, s3_key, ExtraArgs=extra_args
            )
            logger.info(f"👌Successfully uploaded {file_path} to {s3_key}")
            return True

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_msg = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"🔥Failed to upload {file_path}. Error code: {error_code}, Message: {error_msg}")
            return False
        except Exception as e:
            logger.error(f"💥Unexpected error uploading {file_path}: {str(e)}")
            return False

    def upload_fileobj(
        self, file_obj: BinaryIO, s3_key: str, extra_args: dict = None
    ) -> bool:
        """
        Upload a file-like object to S3 bucket.

        Args:
            file_obj: File-like object to upload
            s3_key: Destination path in S3
            extra_args: Additional arguments like ContentType, ACL, etc.

        Returns:
            bool: True if upload was successful, False otherwise
        """
        try:
            extra_args = extra_args or {}

            self.s3_client.upload_fileobj(
                file_obj, self.bucket_name, s3_key, ExtraArgs=extra_args
            )
            logger.info(f"👌Successfully uploaded file object to {s3_key}")
            return True

        except ClientError as e:
            logger.error(f"🔥Failed to upload file object: {str(e)}")
            return False

    def download_file(self, s3_key: str, local_path: Union[str, Path]) -> bool:
        """
        Download a file from S3 bucket.

        Args:
            s3_key: Source path in S3
            local_path: Local destination path

        Returns:
            bool: True if download was successful, False otherwise
        """
        try:
            local_path = str(local_path)

            # Check if file exists in S3
            try:
                self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            except ClientError as e:
                if e.response["Error"]["Code"] == "404":
                    logger.error(f"File does not exist in S3: {s3_key}")
                    return False
                else:
                    raise

            # Create directory if it doesn't exist
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)

            # Check if directory is writable
            if not os.access(Path(local_path).parent, os.W_OK):
                logger.error(f"Directory is not writable: {Path(local_path).parent}")
                return False

            self.s3_client.download_file(self.bucket_name, s3_key, local_path)
            
            # Verify file was downloaded
            if not Path(local_path).exists():
                logger.error(f"File was not downloaded to {local_path}")
                return False
                
            logger.info(f"👏Successfully downloaded {s3_key} to {local_path}")
            return True

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_msg = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"🔥Failed to download {s3_key}. Error code: {error_code}, Message: {error_msg}")
            return False
        except Exception as e:
            logger.error(f"💥Unexpected error downloading {s3_key}: {str(e)}")
            return False

    def generate_presigned_url(
        self, s3_key: str, expiration: int = 3600, http_method: str = "GET"
    ) -> Optional[str]:
        """
        Generate a presigned URL for an S3 object.

        Args:
            s3_key: Path to the object in S3
            expiration: Time in seconds until the URL expires
            http_method: HTTP method to allow ('GET' or 'PUT')

        Returns:
            str: Presigned URL or None if generation fails
        """
        try:
            logger.info(f"💫 Generating presigned URL for S3 key: {s3_key}")
            logger.info(f"💫 Bucket name: {self.bucket_name}")
            logger.info(f"💫 AWS Region: {self.s3_client.meta.region_name}")
            
            # Check if file exists first
            try:
                self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
                logger.info("💫 File exists in S3")
            except ClientError as e:
                if e.response["Error"]["Code"] == "404":
                    logger.error(f"💫 File does not exist in S3: {s3_key}")
                    logger.error(f"💫 Error response: {e.response}")
                    return None
                else:
                    raise

            url = self.s3_client.generate_presigned_url(
                "get_object" if http_method == "GET" else "put_object",
                Params={"Bucket": self.bucket_name, "Key": s3_key},
                ExpiresIn=expiration,
            )
            logger.info(f"👌Generated presigned URL: {url}")
            return url

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_msg = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"🔥Failed to generate presigned URL for {s3_key}. Error code: {error_code}, Message: {error_msg}")
            logger.error(f"🔥Full error response: {e.response}")
            return None
        except Exception as e:
            logger.error(f"💥Unexpected error generating presigned URL for {s3_key}: {str(e)}")
            return None

    def check_file_exists(self, s3_key: str) -> bool:
        """
        Check if a file exists in the S3 bucket.

        Args:
            s3_key: Path to the object in S3

        Returns:
            bool: True if file exists, False otherwise
        """
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            else:
                logger.error(f"🔥Error checking if file exists: {str(e)}")
                return False


s3_utils = S3Utils(
    bucket_name=settings.AWS_BUCKET,
    aws_access_key_id=settings.AWS_KEY,
    aws_secret_access_key=settings.AWS_SECRET,
    region_name=settings.AWS_REGION,
)  # noqa
