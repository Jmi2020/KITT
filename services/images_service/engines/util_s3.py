"""
Shared MinIO/S3 storage utilities
"""
import io
import os
import json
import time
import uuid
import boto3


class S3Store:
    """MinIO/S3 storage handler for generated images and metadata"""

    def __init__(self):
        self.client = boto3.client(
            "s3",
            endpoint_url=os.getenv("S3_ENDPOINT_URL"),
            aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
            region_name=os.getenv("S3_REGION"),
        )
        self.bucket = os.getenv("S3_BUCKET")
        self.prefix = os.getenv("S3_PREFIX", "images/")

    def save_png_and_bytes(self, png_bytes: bytes, meta: dict) -> dict:
        """Save PNG bytes and JSON metadata to S3, return keys"""
        ts = time.strftime("%Y%m%d_%H%M%S")
        key_base = f"{self.prefix}{ts}_{uuid.uuid4().hex[:8]}"
        png_key = f"{key_base}.png"
        meta_key = f"{key_base}.json"

        # Upload PNG
        self.client.put_object(
            Bucket=self.bucket,
            Key=png_key,
            Body=png_bytes,
            ContentType="image/png"
        )

        # Upload metadata
        self.client.put_object(
            Bucket=self.bucket,
            Key=meta_key,
            Body=json.dumps(meta, indent=2).encode("utf-8"),
            ContentType="application/json"
        )

        return {"png_key": png_key, "meta_key": meta_key}
