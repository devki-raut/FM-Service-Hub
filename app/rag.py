from app.config import get_settings
from app.mistral_client import MistralService
from app.models import ChatRequest, ChatResponse, Source
from app.search_store import SearchStore


SYSTEM_PROMPT = """You are the FM Service Hub RFQ assistant.
Answer only from the retrieved source excerpts.
If the answer is not supported by the excerpts, say that the documents do not provide enough information.
For Excel aggregate or count questions, prefer Excel summary excerpts first, then row excerpts for examples or details.
Be concise, business-ready, and include document names in the answer when useful."""

EXCEL_TERMS = {"branch", "complaint", "complaints", "count", "critical", "customer", "division", "equipment", "excel", "market", "overall", "rows", "sheet", "status", "total", "warranty", "cx2000"}


class RagService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._mistral = MistralService()
        self._search = SearchStore()

    async def answer(self, request: ChatRequest) -> ChatResponse:
        top_k = max(self._settings.top_k, 5)
        filter_expression = _filter_for_question(request.question)
        query_embedding = (await self._mistral.embed([request.question]))[0]
        matches = self._search.search(
            request.question,
            query_embedding,
            top_k=top_k,
            filter_expression=filter_expression,
        )
        sources = [_source_from_result(match) for match in matches]

        context = "\n\n".join(_format_source(index, source) for index, source in enumerate(sources, start=1))
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Question:\n{request.question}\n\nSource excerpts:\n{context}",
            },
        ]
        answer = await self._mistral.complete(messages)
        return ChatResponse(answer=answer, sources=sources)


def _filter_for_question(question: str) -> str | None:
    lowered = question.lower()
    if any(term in lowered for term in EXCEL_TERMS):
        return "file_type eq 'excel'"
    return None


def _source_from_result(result: dict) -> Source:
    return Source(
        document_name=result.get("document_name", ""),
        page=result.get("page"),
        section=result.get("section"),
        score=result.get("@search.score"),
        content=result.get("content", ""),
    )


def _format_source(index: int, source: Source) -> str:
    location_parts = [source.document_name]
    if source.page:
        location_parts.append(f"page/slide {source.page}")
    if source.section:
        location_parts.append(source.section)
    location = ", ".join(location_parts)
    return f"[{index}] {location}\n{source.content}"





