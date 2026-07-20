import asyncio

from app.models import ChatRequest
from app.rag import MISSING_DATA_ANSWER, RagService, SYSTEM_PROMPT


class FakeMistral:
    async def embed(self, texts):
        return [[0.0] for _ in texts]


class EmptySearch:
    def search(self, query, embedding, top_k, filter_expression=None):
        return []


def test_rag_returns_exact_missing_data_answer_when_no_sources():
    service = object.__new__(RagService)
    service._settings = type("Settings", (), {"top_k": 5})()
    service._mistral = FakeMistral()
    service._search = EmptySearch()

    response = asyncio.run(service.answer(ChatRequest(question="Unknown question")))

    assert response.answer == MISSING_DATA_ANSWER
    assert response.sources == []


def test_system_prompt_contains_alignment_and_conciseness_rules():
    assert "answer strictly from the retrieved source excerpts" in SYSTEM_PROMPT
    assert MISSING_DATA_ANSWER in SYSTEM_PROMPT
    assert "short, precise, and to the point" in SYSTEM_PROMPT
    assert "Use extractive wording" in SYSTEM_PROMPT
    assert "do not add qualifiers" in SYSTEM_PROMPT
    assert "Use this answer format for count questions" in SYSTEM_PROMPT
    assert "Do not include source or excerpt labels" in SYSTEM_PROMPT
    assert "*(Source: Excerpt [n])*" not in SYSTEM_PROMPT





class ExcelSearchShouldNotRun:
    def search(self, query, embedding, top_k, filter_expression=None):
        raise AssertionError("Excel aggregate questions should bypass vector search")


def test_rag_uses_excel_agent_before_vector_search():
    service = object.__new__(RagService)
    service._settings = type("Settings", (), {"top_k": 5})()
    service._mistral = FakeMistral()
    service._search = ExcelSearchShouldNotRun()

    response = asyncio.run(service.answer(ChatRequest(question="What is the overall count Of complaints for CX2000 for 2025?")))

    assert "**1285 rows**" in response.answer
