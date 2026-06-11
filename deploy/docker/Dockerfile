# gfmrag extractor image — multi-stage: build on CUDA *devel* (needs nvcc to
# pre-compile ColBERT extensions), ship on the slimmer CUDA *runtime* base.
# Build context = repo root:
#   gcloud builds submit --config deploy/cloudbuild/extractor.yaml --substitutions _IMAGE=... .

# ---- builder: full toolkit, installs deps + bakes the CUDA JIT extensions ----
FROM nvidia/cuda:12.6.3-devel-ubuntu24.04 AS builder

ENV PYTHONUNBUFFERED=1 \
    POETRY_VERSION=2.4.1 \
    POETRY_VIRTUALENVS_CREATE=false \
    CUDA_HOME=/usr/local/cuda \
    VIRTUAL_ENV=/venv \
    PATH="/venv/bin:$PATH" \
    TORCH_CUDA_ARCH_LIST=8.9 \
    TORCH_EXTENSIONS_DIR=/opt/torch_ext

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-dev build-essential ninja-build git curl && \
    rm -rf /var/lib/apt/lists/* && \
    python3 -m venv /venv
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR /app
COPY pyproject.toml poetry.lock README.md ./
COPY gfmrag ./gfmrag
RUN poetry install --only main --extras faiss-gpu --no-interaction --no-ansi
RUN python -c "import numpy, torch, transformers; print('deps ok:', torch.__version__)"

# Pre-compile ColBERT/pylate CUDA extensions into /opt/torch_ext (no GPU needed;
# targets L4 via TORCH_CUDA_ARCH_LIST). Saves ~84s per cold run AND removes the
# runtime need for nvcc — see bake_extensions.py.
COPY deploy/docker/bake_extensions.py /tmp/bake_extensions.py
RUN python /tmp/bake_extensions.py

# ---- runtime: slim CUDA runtime base, no toolkit/compiler ----
FROM nvidia/cuda:12.6.3-runtime-ubuntu24.04 AS runtime

ENV PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/venv \
    PATH="/venv/bin:$PATH" \
    CUDA_HOME=/usr/local/cuda \
    TORCH_EXTENSIONS_DIR=/opt/torch_ext

# python3 to back the venv symlinks; curl for the metadata ID-token fetch the
# job's command does. No build-essential / ninja / nvcc — extensions are baked.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /venv /venv
COPY --from=builder /opt/torch_ext /opt/torch_ext

WORKDIR /app
COPY pyproject.toml poetry.lock README.md ./
COPY gfmrag ./gfmrag

# Default = build the graph index (NER + OpenIE). The job overrides with a
# shell command (dataset, backend, metadata-token fetch).
ENTRYPOINT ["python", "-m", "gfmrag.workflow.index_dataset"]
