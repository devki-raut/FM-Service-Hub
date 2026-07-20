from app.chunking import chunk_records


def test_chunk_records_keeps_metadata():
    records = [
        {
            "text": "First paragraph.\n\nSecond paragraph.",
            "metadata": {
                "document_name": "RFQ.pdf",
                "source_path": "RFQ.pdf",
                "page": 1,
                "section": None,
                "file_type": "pdf",
            },
        }
    ]

    chunks = chunk_records(records)

    assert chunks
    assert chunks[0]["metadata"]["document_name"] == "RFQ.pdf"
    assert chunks[0]["metadata"]["chunk_id"] == 0
