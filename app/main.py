import base64

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
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
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def fmservicehub_home() -> str:
    return """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>FM Service Hub</title>
      </head>
      <body>
        <main>
          <h1>FM Service Hub</h1>
          <p>FM Service Hub is an Emergys Solutions Teams app for answering questions from configured FM Service Hub documents.</p>
          <p><a href="/fmservicehub-poc/privacy">Privacy Policy</a> | <a href="/fmservicehub-poc/terms">Terms of Use</a></p>
        </main>
      </body>
    </html>
    """


@app.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
async def fmservicehub_privacy() -> str:
    return """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Privacy Policy - FM Service Hub</title>
      </head>
      <body>
        <main>
          <h1>Privacy Policy</h1>
          <p>FM Service Hub is provided by Emergys Solutions for authorized users.</p>
          <p>The app processes user questions and configured FM Service Hub document content to generate responses. It does not sell personal data.</p>
          <p>Access to the app is controlled by the configured Microsoft Teams and Azure authentication settings.</p>
          <p>For privacy questions, contact Emergys Solutions.</p>
        </main>
      </body>
    </html>
    """


@app.get("/terms", response_class=HTMLResponse, include_in_schema=False)
async def fmservicehub_terms() -> str:
    return """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Terms of Use - FM Service Hub</title>
      </head>
      <body>
        <main>
          <h1>Terms of Use</h1>
          <p>FM Service Hub is intended for authorized business use only.</p>
          <p>Users are responsible for validating AI-generated answers before relying on them for business decisions.</p>
          <p>The app and its outputs are provided according to the applicable agreement with Emergys Solutions.</p>
          <p>Do not use the app to submit sensitive information unless your organization has approved that use.</p>
        </main>
      </body>
    </html>
    """


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

