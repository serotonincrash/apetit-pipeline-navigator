"""Object storage over the S3 API (MinIO locally and on the VM): package files and artifacts.

Artifacts are Parquet files under `runs/<run_id>/<artifact_id>.parquet`. Raw package files
keep their package path under `package/`.
"""

import hashlib
import io
from functools import lru_cache

import pandas as pd
from minio import Minio

from navigator.settings import get_settings


@lru_cache
def get_client() -> Minio:
    s = get_settings()
    return Minio(
        s.s3_endpoint,
        access_key=s.minio_root_user,
        secret_key=s.minio_root_password,
        secure=s.s3_secure,
    )


def ensure_bucket(bucket: str) -> None:
    client = get_client()
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def put_bytes(bucket: str, key: str, content: bytes) -> str:
    get_client().put_object(bucket, key, io.BytesIO(content), len(content))
    return f"s3://{bucket}/{key}"


def get_bytes(uri: str) -> bytes:
    bucket, key = split_uri(uri)
    response = get_client().get_object(bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def split_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"not an s3 uri: {uri}")
    bucket, _, key = uri.removeprefix("s3://").partition("/")
    return bucket, key


def frame_to_parquet(frame: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    frame.to_parquet(buffer, index=False)
    return buffer.getvalue()


def parquet_to_frame(content: bytes) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(content))


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def package_key(path: str) -> str:
    return f"package/{path}"


def artifact_key(run_id: str, artifact_id: str) -> str:
    return f"runs/{run_id}/{artifact_id}.parquet"
