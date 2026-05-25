from urllib.parse import parse_qs, urlparse

from app.services import storage_service


def test_presigned_download_uses_aws_signature_v4(monkeypatch):
    monkeypatch.setattr(storage_service, "_s3", None)
    monkeypatch.setattr(
        storage_service.settings,
        "STORAGE_ENDPOINT_URL",
        "https://project.storage.supabase.co/storage/v1/s3",
    )
    monkeypatch.setattr(storage_service.settings, "STORAGE_ACCESS_KEY_ID", "access-key")
    monkeypatch.setattr(storage_service.settings, "STORAGE_SECRET_ACCESS_KEY", "secret-key")
    monkeypatch.setattr(storage_service.settings, "STORAGE_BUCKET_NAME", "med-materials")

    url = storage_service.get_s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": "med-materials", "Key": "materials/test.pdf"},
        ExpiresIn=3600,
    )
    query = parse_qs(urlparse(url).query)

    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert "X-Amz-Signature" in query
    assert "AWSAccessKeyId" not in query
