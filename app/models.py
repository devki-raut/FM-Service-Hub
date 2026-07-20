from pydantic import BaseModel, Field


class Source(BaseModel):
    document_name: str
    page: int | None = None
    section: str | None = None
    score: float | None = None
    content: str


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]


class HealthResponse(BaseModel):
    status: str
    app: str
