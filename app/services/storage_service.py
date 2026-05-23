import boto3
from app.core.config import settings

s3 = boto3.client(
    "s3",
    endpoint_url=settings.R2_ENDPOINT_URL,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
)


async def upload_to_r2(file_bytes: bytes, key: str, content_type: str) -> str:
    s3.put_object(Bucket=settings.R2_BUCKET_NAME, Key=key, Body=file_bytes, ContentType=content_type)
    return key


async def get_presigned_url(key: str, expires_in: int = 3600) -> str:
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.R2_BUCKET_NAME, "Key": key},
        ExpiresIn=expires_in,
    )
