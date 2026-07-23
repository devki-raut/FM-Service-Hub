from fastapi import APIRouter, Request, Response
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
from botbuilder.schema import Activity, Attachment

from app.config import get_settings
from app.models import ChatRequest
from app.rag import RagService

router = APIRouter()


@router.post("/api/messages")
async def messages(request: Request) -> Response:
    import logging
    logging.warning(f"Received POST /api/messages, auth header present: {bool(request.headers.get('Authorization'))}")
    settings = get_settings()
    logging.warning(f"BOT_APP_ID set: {bool(settings.bot_app_id)}, PASSWORD set: {bool(settings.bot_app_password)}")
    settings = get_settings()
    body = await request.json()
    activity = Activity().deserialize(body)
    auth_header = request.headers.get("Authorization", "")

    adapter_settings = BotFrameworkAdapterSettings(
        app_id=settings.bot_app_id,
        app_password=settings.bot_app_password,
        channel_auth_tenant=settings.azure_ad_tenant_id or None,
    )
    adapter = BotFrameworkAdapter(adapter_settings)
    rag = RagService()

    async def turn_logic(turn_context: TurnContext) -> None:
        import traceback
        text = (turn_context.activity.text or "").strip()
        if not text:
            await turn_context.send_activity("Please send a question about the RFQ or FM Service Hub documents.")
            return
        try:
            response = await rag.answer(ChatRequest(question=text))
        except Exception as e:
            logging.error(f"RAG error: {e}\n{traceback.format_exc()}")
            await turn_context.send_activity(f"Sorry, an error occurred: {type(e).__name__}: {e}")
            return
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

    await adapter.process_activity(activity, auth_header, turn_logic)
    return Response(status_code=201)
