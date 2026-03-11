"""
S3 storage for OTA artifacts. Uploads signed IPA, manifest.plist, and icon to S3.
Uses the official Tencent COS Python SDK (cos-python-sdk-v5) which properly handles
multipart upload with Content-Length headers, unlike generic boto3 on COS.
Public URLs are built from S3_EXTERNAL_DOMAIN (user-facing domain), not the SDK endpoint.
"""
import logging
from pathlib import Path

from config import Config

log = logging.getLogger(__name__)

_MULTIPART_PART_SIZE_MB = 10   # each part: 10 MB
_MULTIPART_THREADS = 4         # concurrent upload threads


def _client():
    """Lazy COS Python SDK client."""
    from qcloud_cos import CosConfig, CosS3Client

    config = CosConfig(
        Region=Config.S3_REGION,
        SecretId=Config.S3_ACCESS_KEY,
        SecretKey=Config.S3_SECRET_KEY,
    )
    return CosS3Client(config)


def object_key(build_uuid: str, filename: str) -> str:
    """Build object key: prefix/build_uuid/filename."""
    prefix = (Config.S3_PREFIX or "ota").strip("/")
    return f"{prefix}/{build_uuid}/{filename}"


def public_url(object_key_str: str) -> str:
    """Return public URL for an object key using S3_EXTERNAL_DOMAIN."""
    return Config.s3_public_url(object_key_str)


def upload_file(local_path: str, object_key_str: str, content_type: str) -> str:
    """
    Upload a local file to COS using the high-level multipart upload API.
    Automatically switches between simple upload (< part threshold) and
    multipart upload (>= part threshold) based on file size.
    Returns the public URL for the object.
    """
    if not Config.S3_BUCKET or not Config.S3_EXTERNAL_DOMAIN:
        raise ValueError("S3_BUCKET and S3_EXTERNAL_DOMAIN must be set")
    path = Path(local_path)
    if not path.exists():
        raise FileNotFoundError(f"Local file not found: {local_path}")

    client = _client()
    extra_args = {}
    if content_type:
        extra_args["ContentType"] = content_type

    try:
        client.upload_file(
            Bucket=Config.S3_BUCKET,
            LocalFilePath=str(path),
            Key=object_key_str,
            PartSize=_MULTIPART_PART_SIZE_MB,
            MAXThread=_MULTIPART_THREADS,
            **extra_args,
        )
    except Exception as e:
        raise RuntimeError(
            f"Failed to upload {local_path} to {Config.S3_BUCKET}/{object_key_str}: {e}"
        ) from e

    return public_url(object_key_str)


def upload_bytes(data: bytes, object_key_str: str, content_type: str) -> str:
    """
    Upload bytes directly to COS (simple PUT). Returns public URL for the object.
    """
    if not Config.S3_BUCKET or not Config.S3_EXTERNAL_DOMAIN:
        raise ValueError("S3_BUCKET and S3_EXTERNAL_DOMAIN must be set")

    client = _client()
    kwargs = {
        "Bucket": Config.S3_BUCKET,
        "Key": object_key_str,
        "Body": data,
    }
    if content_type:
        kwargs["ContentType"] = content_type

    try:
        client.put_object(**kwargs)
    except Exception as e:
        raise RuntimeError(
            f"Failed to upload bytes to {Config.S3_BUCKET}/{object_key_str}: {e}"
        ) from e

    return public_url(object_key_str)


def delete_build_objects(build_uuid: str) -> int:
    """
    Delete all COS objects under prefix/{build_uuid}/.
    Returns the number of objects deleted. Silently skips if S3 is not configured.
    """
    if not Config.S3_BUCKET:
        return 0
    prefix = (Config.S3_PREFIX or "ota").strip("/")
    folder = f"{prefix}/{build_uuid}/"
    try:
        client = _client()
        keys: list[str] = []

        # Paginate through all objects under this build's folder
        marker = ""
        while True:
            list_kwargs = {
                "Bucket": Config.S3_BUCKET,
                "Prefix": folder,
            }
            if marker:
                list_kwargs["Marker"] = marker
            resp = client.list_objects(**list_kwargs)
            for obj in resp.get("Contents", []):
                keys.append(obj["Key"])
            if resp.get("IsTruncated") == "true":
                marker = resp.get("NextMarker", "")
            else:
                break

        if not keys:
            return 0

        # COS delete_objects accepts up to 1000 keys per call
        for i in range(0, len(keys), 1000):
            batch = [{"Key": k} for k in keys[i : i + 1000]]
            client.delete_objects(
                Bucket=Config.S3_BUCKET,
                Delete={"Object": batch, "Quiet": "true"},
            )
        log.info("Deleted %d COS object(s) for build %s", len(keys), build_uuid)
        return len(keys)
    except Exception:
        log.exception("Failed to delete COS objects for build %s", build_uuid)
        return 0
