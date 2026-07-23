from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from app.config import get_settings
from app.models import ChatResponse, Source
from app.rag_constants import MISSING_DATA_ANSWER
from app.source_refs import append_references

AGGREGATE_TERMS = {
    "average",
    "avg",
    "count",
    "counts",
    "highest",
    "how",
    "least",
    "lowest",
    "many",
    "max",
    "maximum",
    "mean",
    "min",
    "minimum",
    "most",
    "number",
    "overall",
    "sum",
    "total",
}
STOPWORDS = {
    "a",
    "an",
    "and",
    "any",
    "are",
    "by",
    "count",
    "counts",
    "data",
    "excel",
    "file",
    "for",
    "from",
    "give",
    "has",
    "how",
    "in",
    "is",
    "many",
    "me",
    "most",
    "number",
    "of",
    "on",
    "overall",
    "please",
    "record",
    "records",
    "row",
    "rows",
    "sheet",
    "show",
    "table",
    "the",
    "there",
    "their",
    "this",
    "to",
    "total",
    "what",
    "which",
    "with",
    "year",
}
COLUMN_ALIASES = {
    "branch": "Branch",
    "status": "Complaint Status",
    "complaint status": "Complaint Status",
    "type": "Comp Type",
    "comp type": "Comp Type",
    "complaint type": "Comp Type",
    "equipment": "Equipment Type",
    "equipment type": "Equipment Type",
    "equipment name": "Equipment Name",
    "customer": "Customer Number ",
    "customer number": "Customer Number ",
    "warranty": "Warranty",
    "market": "Market Vertical",
    "market vertical": "Market Vertical",
    "critical": "Critical",
    "division": "Division",
}


@dataclass(frozen=True)
class ExcelTable:
    path: Path
    sheet_name: str
    frame: pd.DataFrame


def try_answer_excel_question(question: str) -> ChatResponse | None:
    if not _looks_like_excel_aggregate(question):
        return None

    tables = _load_excel_tables()
    if not tables:
        return None

    table_results = []
    for table in tables:
        filtered, filters, date_basis = _apply_filters(question, table)
        group_column = _find_group_column(question, table.frame)
        table_results.append((table, filtered, filters, date_basis, group_column))

    if not table_results:
        return None

    if any(group_column for *_, group_column in table_results):
        return _grouped_count_answer(question, table_results)
    return _count_answer(question, table_results)


def _looks_like_excel_aggregate(question: str) -> bool:
    tokens = set(_tokens(question))
    return bool(tokens & AGGREGATE_TERMS) or "how many" in question.casefold()


@lru_cache(maxsize=1)
def _load_excel_tables() -> tuple[ExcelTable, ...]:
    settings = get_settings()
    root = Path(settings.excel_source_path or ".")
    if not root.is_absolute():
        root = Path.cwd() / root

    files = []
    if root.is_file() and root.suffix.casefold() in {".xlsx", ".xls", ".csv"}:
        files = [root]
    elif root.exists():
        files = sorted(path for path in root.rglob("*") if path.suffix.casefold() in {".xlsx", ".xls", ".csv"})

    tables = []
    for path in files:
        if path.name.startswith("~$"):
            continue
        if path.suffix.casefold() == ".csv":
            frame = pd.read_csv(path, dtype=str).dropna(how="all").fillna("")
            if not frame.empty:
                tables.append(ExcelTable(path, "CSV", frame))
            continue

        sheets = pd.read_excel(path, sheet_name=None, dtype=str)
        for sheet_name, frame in sheets.items():
            frame = frame.dropna(how="all").fillna("")
            if not frame.empty:
                tables.append(ExcelTable(path, sheet_name, frame))
    return tuple(tables)


def _apply_filters(question: str, table: ExcelTable) -> tuple[pd.DataFrame, list[str], str | None]:
    frame = table.frame
    filtered = frame
    filters = []
    date_basis = None

    year = _extract_year(question)
    if year is not None:
        date_column = _select_date_column(question, frame)
        if date_column:
            dates = pd.to_datetime(filtered[date_column], errors="coerce")
            filtered = filtered[dates.dt.year.eq(year)]
            filters.append(f"{date_column} year {year}")
            date_basis = date_column

    for column, value in _matched_column_values(question, filtered):
        filtered = filtered[filtered[column].astype(str).str.casefold() == value.casefold()]
        filters.append(f"{column} = {value}")

    for token in _free_text_tokens(question, filtered, table):
        row_text = _row_text(filtered)
        mask = row_text.str.contains(re.escape(token), case=False, na=False)
        if mask.any():
            filtered = filtered[mask]
            filters.append(f"row text contains {token}")

    return filtered, filters, date_basis


def _extract_year(question: str) -> int | None:
    match = re.search(r"\b(20\d{2})\b", question)
    return int(match.group(1)) if match else None


def _select_date_column(question: str, frame: pd.DataFrame) -> str | None:
    date_columns = [column for column in frame.columns if "date" in str(column).casefold()]
    if not date_columns:
        return None

    lowered = question.casefold()
    if "close date" in lowered or "closed date" in lowered:
        return _first_column_containing(date_columns, "close") or date_columns[0]
    if "created date" in lowered or "create date" in lowered:
        return _first_column_containing(date_columns, "created") or date_columns[0]
    return _first_column_containing(date_columns, "created") or date_columns[0]


def _matched_column_values(question: str, frame: pd.DataFrame) -> list[tuple[str, str]]:
    normalized_question = _normalize_text(question)
    matches = []
    for column in frame.columns:
        values = frame[column].dropna().astype(str).str.strip()
        if values.empty or values.nunique() > 200 or values.str.len().mean() > 80:
            continue
        for value in sorted(values.unique(), key=len, reverse=True):
            normalized_value = _normalize_text(value)
            if not normalized_value or len(normalized_value) < 2 or normalized_value.isdigit():
                continue
            if re.search(rf"\b{re.escape(normalized_value)}\b", normalized_question):
                matches.append((column, value))
                break
    return matches


def _free_text_tokens(question: str, frame: pd.DataFrame, table: ExcelTable) -> list[str]:
    column_tokens = set()
    for column in frame.columns:
        column_tokens.update(_tokens(str(column)))

    value_tokens = set()
    for _, value in _matched_column_values(question, frame):
        value_tokens.update(_tokens(value))

    year = _extract_year(question)
    filename_tokens = set(_tokens(table.path.stem)) | set(_tokens(table.sheet_name))
    ignored = STOPWORDS | column_tokens | value_tokens | filename_tokens
    if year is not None:
        ignored.add(str(year))
    return [token for token in _tokens(question) if len(token) >= 3 and token not in ignored]


def _find_group_column(question: str, frame: pd.DataFrame) -> str | None:
    normalized_question = _normalize_text(question)
    asks_group = " by " in f" {question.casefold()} " or " per " in f" {question.casefold()} "
    asks_rank = bool(set(_tokens(question)) & {"highest", "least", "lowest", "most", "maximum", "minimum"})
    if not asks_group and not asks_rank:
        return None

    for alias, column in COLUMN_ALIASES.items():
        if alias in normalized_question and column in frame.columns:
            return column
    for column in frame.columns:
        normalized_column = _normalize_text(str(column))
        if normalized_column and normalized_column in normalized_question:
            return column
    return None


def _count_answer(question: str, table_results: list[tuple[ExcelTable, pd.DataFrame, list[str], str | None, str | None]]) -> ChatResponse:
    lines = []
    sources = []
    for table, filtered, filters, date_basis, _ in table_results:
        unique_column = _first_column_containing(list(filtered.columns), "complaint no")
        unique_clause = ""
        if unique_column:
            unique_clause = f" (or **{filtered[unique_column].nunique()} unique {unique_column}**)"

        subject = _subject_from_question(question)
        period = _period_from_filters(filters)
        basis = date_basis or "matching Excel filters"
        lines.append(f"The overall count of {subject} for {period} is **{len(filtered)} rows**{unique_clause} based on the **{basis}**.")
        sources.append(_source_for_table(table, filtered, filters))

    if len(lines) == 1:
        return ChatResponse(answer=append_references(lines[0], sources), sources=sources)
    total = sum(len(filtered) for _, filtered, *_ in table_results)
    return ChatResponse(answer=append_references(f"The overall matching Excel count is **{total} rows**.", sources), sources=sources)


def _grouped_count_answer(question: str, table_results: list[tuple[ExcelTable, pd.DataFrame, list[str], str | None, str | None]]) -> ChatResponse:
    lines = []
    sources = []
    for table, filtered, filters, _, group_column in table_results:
        if not group_column:
            continue
        counts = filtered[group_column].replace("", "(blank)").value_counts().head(20)
        if counts.empty:
            lines.append(f"No matching rows found by {group_column}.")
        else:
            rendered = "; ".join(f"{label}: {count}" for label, count in counts.items())
            lines.append(f"Count by {group_column}: {rendered}.")
        sources.append(_source_for_table(table, filtered, filters))

    if not lines:
        return ChatResponse(answer=MISSING_DATA_ANSWER, sources=[])
    return ChatResponse(answer=append_references("\n".join(lines), sources), sources=sources)


def _source_for_table(table: ExcelTable, filtered: pd.DataFrame, filters: list[str]) -> Source:
    filter_text = "; ".join(filters) if filters else "no filters"
    return Source(
        document_name=table.path.name,
        section=f"{table.sheet_name} pandas result",
        content=f"Computed with pandas from {len(table.frame)} sheet rows; matching rows: {len(filtered)}; filters: {filter_text}.",
    )


def _subject_from_question(question: str) -> str:
    lowered = question.casefold()
    if "complaint" in lowered and "cx2000" in lowered:
        return "complaints for CX2000"
    if "complaint" in lowered:
        return "complaints"
    return "matching Excel rows"


def _period_from_filters(filters: list[str]) -> str:
    for item in filters:
        match = re.search(r"year (20\d{2})", item)
        if match:
            return match.group(1)
    return "the matching data"


def _row_text(frame: pd.DataFrame) -> pd.Series:
    return pd.Series([" ".join(row) for row in frame.astype(str).to_numpy()], index=frame.index)


def _first_column_containing(columns: list[str], needle: str) -> str | None:
    return next((column for column in columns if needle in str(column).casefold()), None)


def _normalize_text(value: str) -> str:
    return " ".join(_tokens(value))


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.casefold())


