from pathlib import Path

from app.document_loaders import load_document


def test_load_excel_adds_summary_records_for_rag_counts():
    records = load_document(Path("FM SERVICE HUB") / "Vendor Copy of CX2000 Complaints 26.xlsx")
    summaries = [record for record in records if "summary" in record["metadata"]["section"]]

    assert summaries
    assert any("Created Date year counts: 2025: 1285 rows" in record["text"] for record in summaries)
    assert any("CX2000" in record["text"] and "2025: 18 rows" in record["text"] for record in summaries)
