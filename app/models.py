from pydantic import BaseModel, Field


class Source(BaseModel):
    document_name: str
    page: int | None = None
    section: str | None = None
    score: float | None = None
    content: str
    source_url: str | None = None


class ImageReference(BaseModel):
    document_name: str
    page: int
    url: str
    data_url: str | None = None
    caption: str | None = None


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    images: list[ImageReference] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    app: str
