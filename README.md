# FM Service Hub RAG Bot

FastAPI RAG bot scaffold for the RFQ/FM Service Hub documents.

## Stack

- Backend: FastAPI
- LLM: Mistral Medium 3.5
- Embeddings: Mistral Embeddings
- Vector database: Azure AI Search
- Parsing: PyMuPDF, LangChain text splitter, Pandas, OpenPyXL, python-pptx
- Storage: Azure Blob Storage
- Deployment: Azure App Service or Azure Container Apps
- Teams: Microsoft Bot Framework
- Auth: Microsoft Entra ID / Azure AD JWT validation

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Fill `.env`, then create the Azure AI Search index and ingest the local RFQ/FM files:

```powershell
python scripts/create_search_index.py
python scripts/ingest_documents.py --path "."
```

Run the API:

```powershell
uvicorn app.main:app --reload --port 8000
```

Ask a question:

```powershell
curl -X POST http://localhost:8000/api/chat `
  -H "Content-Type: application/json" `
  -d "{\"question\":\"Summarize the FM Service Hub requirements from the RFQ.\"}"
```

## Streamlit Client App

Run the app:

```powershell
streamlit run streamlit_app.py
```

The app opens a single FM Service Hub assistant experience for client walkthroughs.

## Teams Endpoint

Configure the Bot Framework messaging endpoint as:

```text
https://<your-host>/fmservicehub-poc/api/messages
```

Set `PUBLIC_BASE_URL` to the same externally reachable app base URL, including any path prefix:

```text
PUBLIC_BASE_URL=https://<your-host>/fmservicehub-poc
```

Teams fetches image attachments separately, so generated diagram URLs must be public HTTPS URLs that Teams can reach.

The same retrieval pipeline is used for the REST chat endpoint and Teams.
