import re

from app.config import get_settings
from app.excel_agent import try_answer_excel_question
from app.mistral_client import MistralService
from app.models import ChatRequest, ChatResponse, Source
from app.rag_constants import MISSING_DATA_ANSWER
from app.search_store import SearchStore



SYSTEM_PROMPT = f"""You are the FM Service Hub RFQ assistant.
Accuracy and alignment: answer strictly from the retrieved source excerpts in the knowledge bank.
Do not infer, estimate, calculate beyond the excerpts, or use outside knowledge.
Use extractive wording: preserve the source document terminology and do not add qualifiers, interpretations, or alternate phrases not present in the excerpts.
For definition, purpose, or "why" questions, answer with the closest supported source wording in 1-3 short sentences.
Missing data protocol: if the source excerpts do not contain enough information, state exactly: {MISSING_DATA_ANSWER}
Conciseness: keep answers short, precise, and to the point.
For Excel aggregate or count questions, prefer Excel summary excerpts first, then row excerpts for examples or details.
Use this answer format for count questions:
The overall count of <subject> for <period> is **<row count> rows** (or **<unique count> unique <identifier>**) based on the **<basis column>** year counts.
Do not include source or excerpt labels in the answer text; sources are returned separately.

If the excerpt only supports one count, omit the parenthetical unique-count clause.
"""

EXCEL_FILTER_TERMS = {
    "branch",
    "complaint",
    "complaints",
    "critical",
    "customer",
    "division",
    "excel",
    "market",
    "record",
    "records",
    "row",
    "rows",
    "sheet",
    "status",
    "trip",
    "warranty",
}


class RagService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._mistral = MistralService()
        self._search = SearchStore()

    async def answer(self, request: ChatRequest) -> ChatResponse:
        excel_answer = try_answer_excel_question(request.question)
        if excel_answer:
            return excel_answer

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
        if not sources:
            return ChatResponse(answer=MISSING_DATA_ANSWER, sources=[])

        context = "\n\n".join(_format_source(index, source) for index, source in enumerate(sources, start=1))
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Question:\n{request.question}\n\nSource excerpts:\n{context}",
            },
        ]
        answer = await self._mistral.complete(messages)
        if answer.strip().casefold() == MISSING_DATA_ANSWER.casefold():
            return ChatResponse(answer=MISSING_DATA_ANSWER, sources=[])
        return ChatResponse(answer=answer, sources=sources)


def _filter_for_question(question: str) -> str | None:
    lowered = question.casefold()
    tokens = set(re.findall(r"[a-z0-9]+", lowered))
    asks_excel = False

    if "excel" in tokens or "sheet" in tokens:
        asks_excel = True
    if "complaint no" in lowered or "complaint number" in lowered:
        asks_excel = True
    if {"complaint", "complaints"} & tokens:
        asks_excel = True
    if ({"row", "rows", "record", "records"} & tokens) and (EXCEL_FILTER_TERMS & tokens):
        asks_excel = True
    if asks_excel:
        return "file_type eq 'excel'"

    if "cx2000" in tokens and ({"manual", "pdf", "document", "doc"} & tokens):
        return "document_name eq 'CX2000 Users Manual.pdf'"
    if "cx2000" in tokens:
        return "file_type ne 'excel'"
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








