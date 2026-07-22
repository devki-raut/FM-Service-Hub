import logging

from fastapi import APIRouter, Request, Response
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
from botbuilder.schema import Activity, Attachment

from app.config import get_settings
from app.models import ChatRequest
from app.rag import RagService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/messages")
@router.post("/fmservicehub-poc/api/messages")
async def messages(request: Request) -> Response:
    settings = get_settings()
    body = await request.json()
    activity = Activity().deserialize(body)
    auth_header = request.headers.get("Authorization", "")

    adapter_settings = BotFrameworkAdapterSettings(settings.bot_app_id, settings.bot_app_password)
    adapter = BotFrameworkAdapter(adapter_settings)
    rag = RagService()

    async def turn_logic(turn_context: TurnContext) -> None:
        text = (turn_context.activity.text or "").strip()
        if not text:
            await turn_context.send_activity("Please send a question about the RFQ or FM Service Hub documents.")
            return
        response = await rag.answer(ChatRequest(question=text))
        await turn_context.send_activity(response.answer)
        if response.images:
            base_url = str(request.base_url).rstrip("/")
            for image in response.images:
                attachment = Attachment(
                    content_type="image/png",
                    content_url=f"{base_url}{image.url}",
                    name=image.caption or image.document_name,
                )
                await turn_context.send_activity(Activity(type="message", attachments=[attachment]))

    try:
        await adapter.process_activity(activity, auth_header, turn_logic)
    except Exception:
        logger.exception('Teams bot message handling failed')
        raise
    return Response(status_code=201)



