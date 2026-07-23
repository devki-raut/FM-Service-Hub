import re

from app.config import get_settings
from app.excel_agent import try_answer_excel_question
from app.mistral_client import MistralService
from app.models import ChatRequest, ChatResponse, Source
from app.rag_constants import MISSING_DATA_ANSWER
from app.search_store import SearchStore
from app.source_refs import append_references
from app.visuals import images_for_question


SYSTEM_PROMPT = f"""You are the FM Service Hub RFQ assistant.
Accuracy and alignment: answer strictly from the retrieved source excerpts in the knowledge bank.
Do not infer, estimate, calculate beyond the excerpts, or use outside knowledge.
Use extractive wording: preserve the source document terminology and do not add qualifiers, interpretations, or alternate phrases not present in the excerpts.
For definition, purpose, or "why" questions, answer with the closest supported source wording in 1-3 short sentences.
Missing data protocol: if the source excerpts do not contain enough information, state exactly: {MISSING_DATA_ANSWER}
Completeness: for procedure, process, installation, commissioning, calibration, maintenance, troubleshooting, or step-by-step questions, include every step present in the relevant source excerpts, in the same order. Do not merge, skip, summarize away, renumber incorrectly, or omit warnings/notes that are part of the procedure.
Word-for-word procedures: when the source uses numbered or bulleted steps, reproduce the step wording as closely as possible from the excerpts. Keep original technical terms, values, labels, cautions, and sequence words.
Conciseness: keep simple factual answers short, but do not shorten procedural answers if doing so would remove a step or required detail.
Visual support: when the question asks for an image, layout, diagram, figure, or visual, answer briefly in text; relevant images are returned separately by the application.
For Excel aggregate or count questions, prefer Excel summary excerpts first, then row excerpts for examples or details.
Use this answer format for count questions:
The overall count of <subject> for <period> is **<row count> rows** (or **<unique count> unique <identifier>**) based on the **<basis column>** year counts.
Source labels may be used when they help show where a step or fact came from. The application also appends a Reference section.

If the excerpt only supports one count, omit the parenthetical unique-count clause.
"""

STEP_QUERY_TERMS = {
    "calibration",
    "commissioning",
    "configure",
    "configuration",
    "install",
    "installation",
    "maintenance",
    "procedure",
    "process",
    "setup",
    "step",
    "steps",
    "troubleshoot",
    "troubleshooting",
    "programming",
}

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

        top_k = _top_k_for_question(request.question, self._settings.top_k)
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
        answer = append_references(answer, sources)
        images = images_for_question(request.question, sources)
        return ChatResponse(answer=answer, sources=sources, images=images)


def _top_k_for_question(question: str, configured_top_k: int) -> int:
    tokens = set(re.findall(r"[a-z0-9]+", question.casefold()))
    if STEP_QUERY_TERMS & tokens:
        return max(configured_top_k, 10)
    return max(configured_top_k, 5)


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
        source_url=result.get("blob_url"),
    )


def _format_source(index: int, source: Source) -> str:
    location_parts = [source.document_name]
    if source.page:
        location_parts.append(f"page/slide {source.page}")
    if source.section:
        location_parts.append(source.section)
    location = ", ".join(location_parts)
    return f"[{index}] {location}\n{source.content}"
