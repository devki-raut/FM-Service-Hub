import argparse
import asyncio
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.chunking import chunk_records
from app.document_loaders import iter_source_files, load_document
from app.mistral_client import MistralService
from app.search_index import create_or_update_index, reset_index
from app.search_store import SearchStore
from app.storage import BlobStorage

DEFAULT_BATCH_SIZE = 64


async def ingest(root: Path, batch_size: int, reset_search_index: bool = False) -> None:
    if reset_search_index:
        reset_index()
    else:
        create_or_update_index()

    mistral = MistralService()
    store = SearchStore()
    storage = BlobStorage()

    source_files = list(iter_source_files(root))
    print(f"Found {len(source_files)} source file(s) under {root}", flush=True)

    indexed_count = 0
    for file_index, path in enumerate(source_files, start=1):
        print(f"[{file_index}/{len(source_files)}] Loading {path}", flush=True)
        records = load_document(path)
        chunks = chunk_records(records)
        print(f"[{file_index}/{len(source_files)}] Prepared {len(chunks)} chunk(s) from {path.name}", flush=True)
        if not chunks:
            continue

        blob_url = storage.upload_file(path)
        batches = _batched(chunks, size=batch_size)
        file_count = 0
        for batch_index, batch in enumerate(batches, start=1):
            print(
                f"[{file_index}/{len(source_files)}] Embedding/uploading batch {batch_index}/{len(batches)} for {path.name}",
                flush=True,
            )
            embeddings = await mistral.embed([chunk["text"] for chunk in batch])
            documents = []
            for chunk, embedding in zip(batch, embeddings, strict=True):
                metadata = chunk["metadata"]
                documents.append(
                    {
                        "id": _document_id(metadata["source_path"], metadata["section"], metadata["chunk_id"], chunk["text"]),
                        "content": chunk["text"],
                        "content_vector": embedding,
                        "document_name": metadata["document_name"],
                        "source_path": metadata["source_path"],
                        "file_type": metadata["file_type"],
                        "page": metadata["page"],
                        "section": metadata["section"],
                        "chunk_id": metadata["chunk_id"],
                        "blob_url": blob_url,
                    }
                )

            store.upload_chunks(documents)
            file_count += len(documents)
            indexed_count += len(documents)

        print(f"Indexed {file_count} chunks from {path}", flush=True)

    print(f"Done. Indexed {indexed_count} chunks.", flush=True)


def _batched(items: list[dict], size: int) -> list[list[dict]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _document_id(source_path: str, section: str | None, chunk_id: int, text: str) -> str:
    digest = hashlib.sha256(f"{source_path}:{section}:{chunk_id}:{text}".encode("utf-8")).hexdigest()
    return digest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest RFQ/FM documents into Azure AI Search.")
    parser.add_argument("--path", default=".", help="Document file or folder to ingest.")
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("INGEST_BATCH_SIZE", DEFAULT_BATCH_SIZE)))
    parser.add_argument(
        "--reset-index",
        action="store_true",
        help="Delete and recreate the Azure AI Search index before ingesting. This removes existing indexed documents.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(ingest(Path(args.path).resolve(), batch_size=args.batch_size, reset_search_index=args.reset_index))

