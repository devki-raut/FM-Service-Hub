import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.search.documents.indexes import SearchIndexClient

from app.config import get_settings


def main() -> None:
    args = parse_args()
    settings = get_settings()
    client = SearchIndexClient(
        endpoint=settings.azure_search_endpoint,
        credential=AzureKeyCredential(settings.azure_search_api_key),
    )

    if args.command == "list":
        list_indexes(client)
    elif args.command == "delete-index":
        delete_index(client, args.name)


def list_indexes(client: SearchIndexClient) -> None:
    service_stats = client.get_service_statistics()
    print("Service statistics:")
    print(_model_to_text(service_stats))
    print()

    index_names = list(client.list_index_names())
    if not index_names:
        print("No indexes found.")
        return

    print("Indexes:")
    for index_name in index_names:
        print(f"- {index_name}")
        try:
            print(_indent(_model_to_text(client.get_index_statistics(index_name))))
        except Exception as exc:
            print(_indent(f"Could not read statistics: {exc}"))


def delete_index(client: SearchIndexClient, index_name: str) -> None:
    try:
        client.delete_index(index_name)
    except ResourceNotFoundError:
        print(f"Index {index_name} was not found.")
        return
    print(f"Deleted index {index_name}.")


def _model_to_text(model: object) -> str:
    if hasattr(model, "as_dict"):
        return str(model.as_dict())
    return str(model)


def _indent(text: str) -> str:
    return "\n".join(f"  {line}" for line in text.splitlines())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect or clean Azure AI Search indexes for this app.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List service/index statistics.")
    delete_parser = subparsers.add_parser("delete-index", help="Delete one Azure AI Search index by name.")
    delete_parser.add_argument("name", help="Index name to delete.")
    return parser.parse_args()


if __name__ == "__main__":
    main()
