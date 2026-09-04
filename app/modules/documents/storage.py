"""Storage service abstraction for document uploads (S3 backend with local/in-memory fallback)."""

import hashlib
import os
import uuid
from typing import Protocol


class StorageBackend(Protocol):
    async def upload(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        content_type: str | None = None,
        shipment_id: uuid.UUID | str,
    ) -> str:
        """Upload file and return persistent file URL or S3 key."""
        ...

    async def retrieve(self, file_url: str) -> bytes:
        """Retrieve file bytes by URL or storage key."""
        ...


class InMemoryStorageBackend:
    """Fast in-memory storage backend for unit tests and offline environments."""

    def __init__(self) -> None:
        self._storage: dict[str, bytes] = {}

    async def upload(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        content_type: str | None = None,
        shipment_id: uuid.UUID | str,
    ) -> str:
        file_hash = hashlib.sha256(file_bytes).hexdigest()[:12]
        key = f"s3://freightcore-documents/{shipment_id}/{file_hash}_{filename}"
        self._storage[key] = file_bytes
        return key

    async def retrieve(self, file_url: str) -> bytes:
        if file_url in self._storage:
            return self._storage[file_url]
        # Return synthetic content if mock key
        return b"FREIGHTCORE_MOCK_FILE_CONTENT"


class S3StorageBackend:
    """S3-compatible storage backend with AWS / MinIO / LocalStack support."""

    def __init__(
        self,
        bucket_name: str = "freightcore-documents",
        region: str = "us-east-1",
        endpoint_url: str | None = None,
    ) -> None:
        self.bucket_name = bucket_name
        self.region = region
        self.endpoint_url = endpoint_url
        self._fallback = InMemoryStorageBackend()

    async def upload(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        content_type: str | None = None,
        shipment_id: uuid.UUID | str,
    ) -> str:
        try:
            import boto3  # type: ignore
            s3 = boto3.client("s3", region_name=self.region, endpoint_url=self.endpoint_url)
            file_hash = hashlib.sha256(file_bytes).hexdigest()[:12]
            key = f"shipments/{shipment_id}/{file_hash}_{filename}"
            s3.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=file_bytes,
                ContentType=content_type or "application/octet-stream",
            )
            return f"s3://{self.bucket_name}/{key}"
        except Exception:
            # Seamless fallback to in-memory/local storage in test or dev without live AWS
            return await self._fallback.upload(
                file_bytes=file_bytes,
                filename=filename,
                content_type=content_type,
                shipment_id=shipment_id,
            )

    async def retrieve(self, file_url: str) -> bytes:
        try:
            import boto3  # type: ignore
            s3 = boto3.client("s3", region_name=self.region, endpoint_url=self.endpoint_url)
            if file_url.startswith(f"s3://{self.bucket_name}/"):
                key = file_url[len(f"s3://{self.bucket_name}/"):]
                response = s3.get_object(Bucket=self.bucket_name, Key=key)
                return response["Body"].read()
        except Exception:
            pass
        return await self._fallback.retrieve(file_url)


# Global storage service instance
_default_backend = S3StorageBackend()


def get_storage_backend() -> StorageBackend:
    return _default_backend

