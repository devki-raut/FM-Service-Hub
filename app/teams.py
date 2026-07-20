from fastapi import APIRouter, Request, Response
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
from botbuilder.schema import Activity

from app.config import get_settings
from app.models import ChatRequest
from app.rag import RagService

router = APIRouter()


@router.post("/api/messages")
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

    await adapter.process_activity(activity, auth_header, turn_logic)
    return Response(status_code=201)
