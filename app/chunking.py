from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import get_settings


def chunk_records(records: list[dict]) -> list[dict]:
    settings = get_settings()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", "; ", " ", ""],
    )

    chunks = []
    for record in records:
        for index, text in enumerate(splitter.split_text(record["text"])):
            metadata = dict(record["metadata"])
            metadata["chunk_id"] = index
            chunks.append({"text": text, "metadata": metadata})
    return chunks

