import asyncio

from app.models import ChatRequest
from app.rag import MISSING_DATA_ANSWER, RagService, SYSTEM_PROMPT, _filter_for_question
from app.search_store import SearchStore


class FakeMistral:
    async def embed(self, texts):
        return [[0.0] for _ in texts]


class EmptySearch:
    def search(self, query, embedding, top_k, filter_expression=None):
        return []


class MissingAnswerMistral(FakeMistral):
    async def complete(self, messages):
        return MISSING_DATA_ANSWER


class LowConfidenceSearch:
    def search(self, query, embedding, top_k, filter_expression=None):
        return [
            {
                "@search.score": 0.031,
                "document_name": "Vendor Copy of CX2000 Complaints 26.xlsx",
                "section": "Complaint Analysis rows 3002-3101",
                "content": "This is a long enough excerpt to pass the minimum content length filter, but it does not contain enough information to answer the question.",
            }
        ]


def test_rag_returns_exact_missing_data_answer_when_no_sources():
    service = object.__new__(RagService)
    service._settings = type("Settings", (), {"top_k": 5})()
    service._mistral = FakeMistral()
    service._search = EmptySearch()

    response = asyncio.run(service.answer(ChatRequest(question="Unknown question")))

    assert response.answer == MISSING_DATA_ANSWER
    assert response.sources == []


def test_rag_does_not_return_sources_when_model_reports_missing_data():
    service = object.__new__(RagService)
    service._settings = type("Settings", (), {"top_k": 5})()
    service._mistral = MissingAnswerMistral()
    service._search = LowConfidenceSearch()

    response = asyncio.run(service.answer(ChatRequest(question="Unsupported question")))

    assert response.answer == MISSING_DATA_ANSWER
    assert response.sources == []



def test_filter_does_not_force_cx2000_manual_questions_to_excel():
    assert _filter_for_question("What is CX2000 equipment commissioning procedure?") is None


def test_filter_limits_explicit_complaint_questions_to_excel():
    assert _filter_for_question("What is the status of complaint AFKK25002022802?") == "file_type eq 'excel'"

def test_filter_routes_explicit_cx2000_manual_questions_to_manual_pdf():
    assert _filter_for_question("From CX2000 Users Manual PDF explain calibration") == "document_name eq 'CX2000 Users Manual.pdf'"


def test_filter_excludes_excel_for_general_cx2000_questions():
    assert _filter_for_question("How to calibrate CX2000?") == "file_type ne 'excel'"


def test_system_prompt_contains_alignment_and_conciseness_rules():
    assert "answer strictly from the retrieved source excerpts" in SYSTEM_PROMPT
    assert MISSING_DATA_ANSWER in SYSTEM_PROMPT
    assert "short, precise, and to the point" in SYSTEM_PROMPT
    assert "Use extractive wording" in SYSTEM_PROMPT
    assert "do not add qualifiers" in SYSTEM_PROMPT
    assert "Use this answer format for count questions" in SYSTEM_PROMPT
    assert "Do not include source or excerpt labels" in SYSTEM_PROMPT
    assert "*(Source: Excerpt [n])*" not in SYSTEM_PROMPT


class FakeSearchClient:
    def search(self, **kwargs):
        long_content = "A relevant excerpt with enough detail to pass the content length filter for search results."
        return [
            {"@search.score": 0.031, "document_name": "low.xlsx", "content": long_content},
            {"@search.score": 0.05, "document_name": "high.pdf", "content": long_content},
        ]


def test_search_store_filters_results_below_min_score():
    store = object.__new__(SearchStore)
    store._client = FakeSearchClient()
    store._min_score = 0.04

    results = store.search("relevant question", [0.0], top_k=5)

    assert [result["document_name"] for result in results] == ["high.pdf"]


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
