from fastapi import Depends, FastAPI

from app.auth import require_user
from app.config import get_settings
from app.models import ChatRequest, ChatResponse, HealthResponse
from app.rag import RagService
from app.teams import router as teams_router

app = FastAPI(title=get_settings().app_name)
app.include_router(teams_router)


def get_rag_service() -> RagService:
    return RagService()


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", app=settings.app_name)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    _: dict = Depends(require_user),
    rag: RagService = Depends(get_rag_service),
) -> ChatResponse:
    return await rag.answer(payload)

