from pathlib import Path

from azure.storage.blob import BlobServiceClient, ContentSettings

from app.config import get_settings


class BlobStorage:
    def __init__(self) -> None:
        settings = get_settings()
        self._container_name = settings.azure_storage_container
        self._client = None

        connection_string = settings.azure_storage_connection_string.strip()
        if not connection_string or "<" in connection_string or "AccountName=" not in connection_string:
            return

        try:
            self._client = BlobServiceClient.from_connection_string(connection_string)
        except ValueError:
            self._client = None

    def upload_file(self, path: Path) -> str | None:
        if not self._client:
            return None
        container = self._client.get_container_client(self._container_name)
        if not container.exists():
            container.create_container()

        blob_name = path.name
        blob_client = container.get_blob_client(blob_name)
        content_type = _content_type(path.suffix.lower())
        with path.open("rb") as handle:
            blob_client.upload_blob(
                handle,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
            )
        return blob_client.url


def _content_type(suffix: str) -> str:
    return {
        ".pdf": "application/pdf",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".csv": "text/csv",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }.get(suffix, "application/octet-stream")
