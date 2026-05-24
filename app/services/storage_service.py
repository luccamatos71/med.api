import asyncio

import boto3
from app.core.config import settings

_s3 = None


def get_s3_client():
    global _s3

    if _s3 is None:
        if not settings.STORAGE_ENDPOINT_URL:
            raise RuntimeError("STORAGE_ENDPOINT_URL is not configured")

        # Supabase Storage exposes an S3-compatible API; boto3 works unchanged.
        # region_name is required by the S3 SDK even though Supabase ignores it.
        _s3 = boto3.client(
            "s3",
            endpoint_url=settings.STORAGE_ENDPOINT_URL,
            aws_access_key_id=settings.STORAGE_ACCESS_KEY_ID,
            aws_secret_access_key=settings.STORAGE_SECRET_ACCESS_KEY,
            region_name="us-east-1",
        )

    return _s3


async def upload_file(file_bytes: bytes, key: str, content_type: str) -> str:
    await asyncio.to_thread(
        get_s3_client().put_object,
        Bucket=settings.STORAGE_BUCKET_NAME,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
    )
    return key


async def get_presigned_url(key: str, expires_in: int = 3600) -> str:
    return await asyncio.to_thread(
        get_s3_client().generate_presigned_url,
        "get_object",
        Params={"Bucket": settings.STORAGE_BUCKET_NAME, "Key": key},
        ExpiresIn=expires_in,
    )
