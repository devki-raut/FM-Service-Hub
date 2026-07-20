import time

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    ExhaustiveKnnAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

from app.config import get_settings

VECTOR_PROFILE = "rag-vector-profile"
VECTOR_ALGORITHM = "exhaustive-knn"


def create_or_update_index() -> None:
    settings = get_settings()
    client = _search_index_client()
    client.create_or_update_index(_search_index(settings.azure_search_index))
    _wait_for_index(client, settings.azure_search_index)


def reset_index() -> None:
    settings = get_settings()
    client = _search_index_client()
    try:
        client.delete_index(settings.azure_search_index)
        print(f"Deleted Azure AI Search index {settings.azure_search_index}.", flush=True)
    except ResourceNotFoundError:
        print(f"Azure AI Search index {settings.azure_search_index} did not exist.", flush=True)

    _wait_for_index_deleted(client, settings.azure_search_index)
    client.create_index(_search_index(settings.azure_search_index))
    _wait_for_index(client, settings.azure_search_index)
    print(f"Created Azure AI Search index {settings.azure_search_index}.", flush=True)


def _wait_for_index(client: SearchIndexClient, index_name: str, timeout_seconds: int = 60) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            client.get_index(index_name)
            return
        except ResourceNotFoundError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(2)


def _wait_for_index_deleted(client: SearchIndexClient, index_name: str, timeout_seconds: int = 60) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            client.get_index(index_name)
        except ResourceNotFoundError:
            return
        if time.monotonic() >= deadline:
            return
        time.sleep(2)


def _search_index_client() -> SearchIndexClient:
    settings = get_settings()
    return SearchIndexClient(
        endpoint=settings.azure_search_endpoint,
        credential=AzureKeyCredential(settings.azure_search_api_key),
    )


def _search_index(index_name: str) -> SearchIndex:
    settings = get_settings()
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="en.lucene"),
        SearchableField(name="document_name", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="source_path", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="file_type", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="page", type=SearchFieldDataType.Int32, filterable=True, facetable=True),
        SearchableField(name="section", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="chunk_id", type=SearchFieldDataType.Int32, filterable=True),
        SimpleField(name="blob_url", type=SearchFieldDataType.String),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=settings.embedding_dimensions,
            vector_search_profile_name=VECTOR_PROFILE,
        ),
    ]

    return SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=VectorSearch(
            algorithms=[ExhaustiveKnnAlgorithmConfiguration(name=VECTOR_ALGORITHM)],
            profiles=[VectorSearchProfile(name=VECTOR_PROFILE, algorithm_configuration_name=VECTOR_ALGORITHM)],
        ),
    )
