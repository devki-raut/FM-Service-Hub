import re
import time

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError, ServiceRequestError, ServiceResponseError
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from app.config import get_settings


QUERY_STOPWORDS = {
    "about",
    "after",
    "all",
    "and",
    "answer",
    "are",
    "can",
    "count",
    "data",
    "describe",
    "does",
    "explain",
    "for",
    "from",
    "give",
    "how",
    "into",
    "many",
    "need",
    "overall",
    "please",
    "procedure",
    "process",
    "show",
    "step",
    "steps",
    "the",
    "this",
    "total",
    "what",
    "when",
    "where",
    "which",
    "why",
    "with",
}


TRANSIENT_UPLOAD_MESSAGES = (
    "unable to get service usage to enforce quota",
    "too many requests",
    "timeout",
    "temporarily unavailable",
)


class SearchStore:
    def __init__(self) -> None:
        settings = get_settings()
        self._min_score = settings.azure_search_min_score
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
        query_terms = _significant_query_terms(query)
        keyword_query = _significant_query_text(query, query_terms)
        vector_query = VectorizedQuery(
            vector=embedding,
            k_nearest_neighbors=fetch_k,
            fields="content_vector",
        )
        selected_fields = [
            "id",
            "content",
            "document_name",
            "source_path",
            "file_type",
            "page",
            "section",
            "chunk_id",
            "blob_url",
        ]
        vector_results = self._client.search(
            search_text=keyword_query,
            vector_queries=[vector_query],
            filter=filter_expression,
            select=selected_fields,
            top=fetch_k,
        )
        keyword_results = self._client.search(
            search_text=keyword_query,
            filter=filter_expression,
            select=selected_fields,
            top=fetch_k,
        )

        candidates = []
        seen_keys = set()
        for source_rank, result_set in enumerate((keyword_results, vector_results), start=1):
            for result in result_set:
                item = dict(result)
                key = item.get("id") or (
                    item.get("document_name"),
                    item.get("page"),
                    item.get("section"),
                    item.get("chunk_id"),
                )
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                score = item.get("@search.score")
                if score is None or score < self._min_score:
                    continue
                content = (item.get("content") or "").strip()
                if len(content) < 80:
                    continue
                searchable_text = " ".join(
                    str(item.get(field) or "") for field in ("document_name", "section", "content")
                )
                overlap = _term_overlap_count(query_terms, searchable_text)
                if query_terms and overlap == 0:
                    continue
                lexical_bonus = 1 if source_rank == 1 else 0
                candidates.append((overlap, lexical_bonus, score, item))

        candidates.sort(key=lambda candidate: (candidate[0], candidate[1], candidate[2]), reverse=True)
        return [item for _, _, _, item in candidates[:top_k]]


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



def _significant_query_terms(query: str) -> set[str]:
    terms = set()
    for token in re.findall(r"[a-z0-9]+", query.casefold()):
        if len(token) >= 3 and token not in QUERY_STOPWORDS:
            terms.add(token)
    return terms


def _term_overlap_count(query_terms: set[str], text: str) -> int:
    if not query_terms:
        return 0
    text_terms = set(re.findall(r"[a-z0-9]+", text.casefold()))
    return len(query_terms & text_terms)

def _significant_query_text(query: str, query_terms: set[str]) -> str:
    if not query_terms:
        return query
    ordered_terms = []
    seen = set()
    for token in re.findall(r"[a-z0-9]+", query.casefold()):
        if token in query_terms and token not in seen:
            ordered_terms.append(token)
            seen.add(token)
    return " ".join(ordered_terms) or query