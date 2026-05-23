import asyncio

import boto3
from app.core.config import settings

# Supabase Storage exposes an S3-compatible API — boto3 works unchanged.
# Endpoint format: https://<project-ref>.supabase.co/storage/v1/s3
# region_name is required by the S3 SDK even though Supabase ignores it.
s3 = boto3.client(
    "s3",
    endpoint_url=settings.STORAGE_ENDPOINT_URL,
    aws_access_key_id=settings.STORAGE_ACCESS_KEY_ID,
    aws_secret_access_key=settings.STORAGE_SECRET_ACCESS_KEY,
    region_name="us-east-1",
)


async def upload_file(file_bytes: bytes, key: str, content_type: str) -> str:
    await asyncio.to_thread(
        s3.put_object,
        Bucket=settings.STORAGE_BUCKET_NAME,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
    )
    return key


async def get_presigned_url(key: str, expires_in: int = 3600) -> str:
    return await asyncio.to_thread(
        s3.generate_presigned_url,
        "get_object",
        Params={"Bucket": settings.STORAGE_BUCKET_NAME, "Key": key},
        ExpiresIn=expires_in,
    )
