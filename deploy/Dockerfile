FROM python:3.11-slim

WORKDIR /app

# System deps for faiss and sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .

# Build demo indexes
RUN python -m connectors.build_demo_index

EXPOSE 8081

CMD ["python", "main.py"]
