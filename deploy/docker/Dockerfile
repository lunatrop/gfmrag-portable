# gfmrag extractor image. Build context = repo root:
#   gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT/gfmrag/extractor:latest -f deploy/docker/Dockerfile .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    POETRY_VERSION=2.4.1 \
    POETRY_VIRTUALENVS_CREATE=false

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR /app

# Dependency layer (cached unless pyproject/lock change). README is required by
# pyproject (readme = "README.md").
COPY pyproject.toml poetry.lock README.md ./
COPY gfmrag ./gfmrag

# Runtime deps only (no dev/docs groups).
RUN poetry install --only main --no-interaction --no-ansi

# Default command = build the graph index (NER + OpenIE extraction).
# Override args via the K8s Job (dataset, backend, model).
ENTRYPOINT ["python", "-m", "gfmrag.workflow.index_dataset"]

# NOTE: this installs the full dep set (incl. faiss-gpu-cu12 / CUDA torch) because
# `import gfmrag` pulls them in. For a lean CPU-only extractor image, build a
# variant that swaps faiss-gpu-cu12 -> faiss-cpu and uses the CPU torch wheel.
