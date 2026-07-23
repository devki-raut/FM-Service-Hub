FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


COPY app ./app
COPY scripts ./scripts
COPY ["FM SERVICE HUB", "./FM SERVICE HUB"]

# Pre-download the fastembed model at build time so the container starts without needing internet access
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-base-en-v1.5', cache_dir='.fastembed_cache')"

EXPOSE 8609

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8609"]
