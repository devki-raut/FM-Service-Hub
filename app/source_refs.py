from app.models import Source
from app.rag_constants import MISSING_DATA_ANSWER


def append_references(answer: str, sources: list[Source], limit: int = 3) -> str:
    if not sources or answer.strip().casefold() == MISSING_DATA_ANSWER.casefold():
        return answer
    if "\nReference:" in answer or "\nReferences:" in answer:
        return answer

    references = format_references(sources, limit=limit)
    if not references:
        return answer
    heading = "Reference" if len(references) == 1 else "References"
    return f"{answer.rstrip()}\n\n{heading}:\n" + "\n".join(f"- {reference}" for reference in references)


def format_references(sources: list[Source], limit: int = 3) -> list[str]:
    references = []
    seen = set()
    for source in sources:
        label = _source_label(source)
        key = (label, source.source_url)
        if key in seen:
            continue
        seen.add(key)
        if source.source_url:
            references.append(f"[{label}]({source.source_url})")
        else:
            references.append(label)
        if len(references) >= limit:
            break
    return references


def _source_label(source: Source) -> str:
    parts = [source.document_name or "Source document"]
    if source.page:
        parts.append(f"page/slide {source.page}")
    if source.section and not _is_generated_excel_section(source):
        parts.append(source.section)
    return ", ".join(parts)


def _is_generated_excel_section(source: Source) -> bool:
    return source.document_name.casefold().endswith((".xlsx", ".xls", ".csv")) and "pandas result" in (source.section or "").casefold()