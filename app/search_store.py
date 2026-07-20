import time

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError, ServiceRequestError, ServiceResponseError
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from app.config import get_settings


TRANSIENT_UPLOAD_MESSAGES = (
    "unable to get service usage to enforce quota",
    "too many requests",
    "timeout",
    "temporarily unavailable",
)


class SearchStore:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = SearchClient(
            endpoint=settings.azure_search_endpoint,
            index_name=settings.azure_search_index,
            credential=AzureKeyCredential(settings.azure_search_api_key),
        )

    def upload_chunks(self, documents: list[dict]) -> None:
        if not documents:
            return

        attempts = 5
        for attempt in range(1, attempts + 1):
            try:
                results = self._client.upload_documents(documents)
                failed = [result for result in results if not result.succeeded]
                if failed:
                    keys = ", ".join(result.key for result in failed[:5])
                    raise RuntimeError(f"Azure AI Search failed to index {len(failed)} document(s). First keys: {keys}")
                return
            except (HttpResponseError, ResourceNotFoundError, ServiceRequestError, ServiceResponseError) as exc:
                if attempt == attempts or not _is_transient_upload_error(exc):
                    raise
                sleep_seconds = min(2 ** attempt, 30)
                print(
                    f"Azure AI Search upload failed transiently ({exc}). "
                    f"Retrying in {sleep_seconds}s ({attempt}/{attempts})...",
                    flush=True,
                )
                time.sleep(sleep_seconds)

    def search(self, query: str, embedding: list[float], top_k: int, filter_expression: str | None = None) -> list[dict]:
        fetch_k = max(top_k * 5, 10)
        vector_query = VectorizedQuery(
            vector=embedding,
            k_nearest_neighbors=fetch_k,
            fields="content_vector",
        )
        results = self._client.search(
            search_text=query,
            vector_queries=[vector_query],
            filter=filter_expression,
            select=[
                "content",
                "document_name",
                "source_path",
                "file_type",
                "page",
                "section",
                "chunk_id",
                "blob_url",
            ],
            top=fetch_k,
        )
        cleaned = []
        for result in results:
            item = dict(result)
            content = (item.get("content") or "").strip()
            if len(content) < 80:
                continue
            cleaned.append(item)
            if len(cleaned) >= top_k:
                break
        return cleaned


def _is_transient_upload_error(exc: Exception) -> bool:
    message = str(exc).casefold()
    if "storage quota has been exceeded" in message:
        return False
    if "index" in message and "not found" in message:
        return True
    if any(transient_message in message for transient_message in TRANSIENT_UPLOAD_MESSAGES):
        return True

    status_code = getattr(exc, "status_code", None)
    return status_code in {408, 409, 429, 500, 502, 503, 504}

