"""Document sources. `LocalFolderSource` (dev) and `S3Source` (prod) both
implement the `DocumentSource` Protocol so the indexer is source-agnostic.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

from app.core.models import DocRef, RawDocument

from ingestion.pipeline.loaders import (
    SUPPORTED_EXTENSIONS,
    filetype_for,
    load_document,
)


class LocalFolderSource:
    """Reads supported files from a local (or mounted) directory tree.

    `doc_id` is the path relative to the root, which is stable across runs and
    becomes the unit of idempotency.
    """

    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    async def list_documents(self):  # -> Sequence[DocRef]
        def _scan() -> list[DocRef]:
            refs: list[DocRef] = []
            for path in sorted(self.root.rglob("*")):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                rel = path.relative_to(self.root).as_posix()
                stat = path.stat()
                refs.append(
                    DocRef(
                        doc_id=rel,
                        source_url=path.as_uri(),
                        filetype=filetype_for(path.name),
                        last_modified=datetime.fromtimestamp(
                            stat.st_mtime, tz=UTC
                        ),
                    )
                )
            return refs

        return await asyncio.to_thread(_scan)

    async def fetch(self, ref: DocRef) -> RawDocument:
        def _read() -> RawDocument:
            path = self.root / ref.doc_id
            data = path.read_bytes()
            title, text = load_document(data, path.name)
            return RawDocument(ref=ref, title=title, text=text, acl=[])

        return await asyncio.to_thread(_read)


class S3Source:
    """Reads supported objects under a bucket/prefix.

    `doc_id` is the object key. ACLs are flat (empty) in v1; when per-document
    permissions are enabled this is where object tags/metadata would populate
    `RawDocument.acl`.
    """

    def __init__(self, bucket: str, prefix: str = "", region: str | None = None) -> None:
        import boto3

        self.bucket = bucket
        self.prefix = prefix
        self._client = boto3.client("s3", region_name=region)

    async def list_documents(self):  # -> Sequence[DocRef]
        def _scan() -> list[DocRef]:
            refs: list[DocRef] = []
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    ext = os.path.splitext(key)[1].lower()
                    if ext not in SUPPORTED_EXTENSIONS:
                        continue
                    refs.append(
                        DocRef(
                            doc_id=key,
                            source_url=f"s3://{self.bucket}/{key}",
                            filetype=filetype_for(key),
                            last_modified=obj.get("LastModified"),
                        )
                    )
            return refs

        return await asyncio.to_thread(_scan)

    async def fetch(self, ref: DocRef) -> RawDocument:
        def _read() -> RawDocument:
            resp = self._client.get_object(Bucket=self.bucket, Key=ref.doc_id)
            data = resp["Body"].read()
            title, text = load_document(data, ref.doc_id)
            return RawDocument(ref=ref, title=title, text=text, acl=[])

        return await asyncio.to_thread(_read)


def build_source():  # -> DocumentSource
    """Construct the configured source from settings."""
    from app.config import get_settings

    s = get_settings()
    if s.doc_source == "s3":
        return S3Source(s.s3_bucket, s.s3_prefix, s.aws_region)
    return LocalFolderSource(s.local_docs_path)
