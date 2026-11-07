"""The seed job: puts the challenge package into object storage and records each file.

    python -m navigator.seed                       # upload from PACKAGE_DIR into S3_BUCKET
    python -m navigator.seed --from-bucket NAME    # copy what another bucket already holds

Runs read the package only from object storage, never from disk. Seeding twice is harmless:
files already recorded with the same checksum are skipped.
"""

import argparse
import hashlib
from pathlib import Path

from minio.commonconfig import CopySource
from sqlalchemy import select

from navigator import ids
from navigator.db import models as m
from navigator.db.session import session_scope
from navigator.logs import configure, get_logger
from navigator.settings import get_settings
from navigator.storage import objects

log = get_logger(__name__)


def _row_count(path: str, content: bytes) -> int | None:
    if path.endswith(".csv"):
        return max(content.count(b"\n") - 1, 0)
    return None


def _record(path: str, sha256: str, size: int, rows: int | None, uri: str) -> None:
    with session_scope() as session:
        existing = session.scalars(select(m.SourceFile).where(m.SourceFile.path == path)).first()
        if existing and existing.sha256 == sha256:
            return
        if existing:
            raise ValueError(f"{path} changed since it was seeded; raw files are never replaced")
        session.add(
            m.SourceFile(
                file_id=ids.new_id("source_file"),
                path=path,
                sha256=sha256,
                bytes=size,
                rows=rows,
                uri=uri,
            )
        )


def seed_from_disk(package_dir: Path, bucket: str) -> int:
    objects.ensure_bucket(bucket)
    count = 0
    for file in sorted(p for p in package_dir.rglob("*") if p.is_file()):
        path = file.relative_to(package_dir).as_posix()
        content = file.read_bytes()
        uri = objects.put_bytes(bucket, objects.package_key(path), content)
        _record(
            path, hashlib.sha256(content).hexdigest(), len(content), _row_count(path, content), uri
        )
        count += 1
    return count


def seed_from_bucket(source_bucket: str, bucket: str) -> int:
    """Copy the package from a bucket filled earlier, for a new worktree's own bucket."""
    client = objects.get_client()
    objects.ensure_bucket(bucket)
    count = 0
    for item in client.list_objects(source_bucket, prefix="package/", recursive=True):
        key = item.object_name
        if key is None:
            continue
        client.copy_object(bucket, key, CopySource(source_bucket, key))
        content = objects.get_bytes(f"s3://{bucket}/{key}")
        path = key.removeprefix("package/")
        _record(
            path,
            hashlib.sha256(content).hexdigest(),
            len(content),
            _row_count(path, content),
            f"s3://{bucket}/{key}",
        )
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-bucket", help="copy the package from this bucket")
    args = parser.parse_args()
    settings = get_settings()
    configure(settings.log_level)
    if args.from_bucket:
        count = seed_from_bucket(args.from_bucket, settings.s3_bucket)
    else:
        count = seed_from_disk(Path(settings.package_dir), settings.s3_bucket)
    log.info("package seeded", extra={"files": count, "bucket": settings.s3_bucket})


if __name__ == "__main__":
    main()
