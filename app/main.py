import base64

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.auth import require_user
from app.config import get_settings
from app.models import ChatRequest, ChatResponse, HealthResponse
from app.rag import RagService
from app.teams import router as teams_router
from app.visuals import VISUAL_ASSET_DIR

app = FastAPI(title=get_settings().app_name)
app.include_router(teams_router)
VISUAL_ASSET_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/assets/visuals", StaticFiles(directory=VISUAL_ASSET_DIR), name="visuals")


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


@app.post("/api/chat/image")
async def chat_image(
    payload: ChatRequest,
    _: dict = Depends(require_user),
    rag: RagService = Depends(get_rag_service),
) -> Response:
    chat_response = await rag.answer(payload)
    if not chat_response.images or not chat_response.images[0].data_url:
        raise HTTPException(status_code=404, detail="No image available for this question")

    data_url = chat_response.images[0].data_url
    _, encoded = data_url.split(",", 1)
    image_bytes = base64.b64decode(encoded)
    return Response(content=image_bytes, media_type="image/png")