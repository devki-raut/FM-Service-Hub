import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.search_index import create_or_update_index


if __name__ == "__main__":
    create_or_update_index()
    print("Azure AI Search index is ready.")
