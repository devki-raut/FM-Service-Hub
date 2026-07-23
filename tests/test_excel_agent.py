from app.excel_agent import try_answer_excel_question


def test_excel_agent_answers_workbook_level_count():
    response = try_answer_excel_question("What is the overall count Of complaints for CX2000 for 2025?")

    assert response is not None
    assert "**1285 rows**" in response.answer
    assert "**1198 unique Complaint No**" in response.answer
    assert "Created Date" in response.answer
    assert response.sources[0].document_name == "Vendor Copy of CX2000 Complaints 26.xlsx"
    assert "Reference:" in response.answer
    assert "Vendor Copy of CX2000 Complaints 26.xlsx" in response.answer
    assert "pandas result" not in response.answer


def test_excel_agent_answers_grouped_count():
    response = try_answer_excel_question("What is the count of complaints by status for 2025?")

    assert response is not None
    assert response.answer.startswith("Count by Complaint Status: CLOSED: 1266; ASSIGNED: 17; OPEN: 2.")
    assert "Reference:" in response.answer


def test_excel_agent_ignores_non_aggregate_question():
    assert try_answer_excel_question("Why measure COD?") is None