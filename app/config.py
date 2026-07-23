from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "FM Service Hub RAG Bot"
    environment: str = "local"

    llm_provider: str = "azure_foundry"
    embedding_provider: str = "fastembed"

    mistral_api_key: str = ""
    mistral_chat_model: str = "mistral-medium-latest"
    mistral_embedding_model: str = "mistral-embed"

    azure_foundry_endpoint: str = ""
    azure_foundry_api_key: str = ""
    azure_foundry_chat_model: str = ""
    azure_foundry_embedding_model: str = ""

    fastembed_model: str = "BAAI/bge-base-en-v1.5"
    fastembed_cache_dir: str = ".fastembed_cache"

    azure_search_endpoint: str = ""
    azure_search_api_key: str = ""
    azure_search_index: str = "fm-service-hub-docs"
    azure_search_min_score: float = Field(default=0.0, ge=0)

    azure_storage_connection_string: str = ""
    azure_storage_container: str = "rag-source-documents"

    azure_ad_tenant_id: str = ""
    azure_ad_audience: str = ""
    auth_required: bool = False

    bot_app_id: str = ""
    bot_app_password: str = ""

    chunk_size: int = Field(default=1200, ge=200)
    chunk_overlap: int = Field(default=180, ge=0)
    top_k: int = Field(default=5, ge=1, le=20)
    embedding_dimensions: int = Field(default=768, ge=1)
    excel_source_path: str = "FM SERVICE HUB"


@lru_cache
def get_settings() -> Settings:
    return Settings()

