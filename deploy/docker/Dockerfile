# gfmrag extractor image. Build context = repo root:
#   gcloud builds submit --config deploy/cloudbuild/extractor.yaml --substitutions _IMAGE=... .
#
# CUDA *devel* base (not python-slim): ColBERT/pylate's PLAID indexer
# JIT-compiles CUDA torch extensions at runtime via torch.utils.cpp_extension,
# which needs nvcc + CUDA headers + CUDA_HOME — pip's nvidia-* runtime libs
# are not enough.
FROM nvidia/cuda:12.6.3-devel-ubuntu24.04

ENV PYTHONUNBUFFERED=1 \
    POETRY_VERSION=2.4.1 \
    POETRY_VIRTUALENVS_CREATE=false \
    CUDA_HOME=/usr/local/cuda

# python3 on ubuntu24.04 = 3.12. Venv sidesteps PEP 668 (externally-managed).
# ninja + python3-dev are needed at RUNTIME for the torch JIT compile.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-dev build-essential ninja-build git curl && \
    rm -rf /var/lib/apt/lists/* && \
    python3 -m venv /venv

# VIRTUAL_ENV makes poetry treat /venv as the active env — without it,
# virtualenvs.create=false resolves to the SYSTEM python (base prefix) and
# deps land where the runtime python never looks.
ENV VIRTUAL_ENV=/venv \
    PATH="/venv/bin:$PATH"
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR /app

# Dependency layer (cached unless pyproject/lock change). README is required by
# pyproject (readme = "README.md").
COPY pyproject.toml poetry.lock README.md ./
COPY gfmrag ./gfmrag

# Runtime deps only (no dev/docs groups). Cloud image -> GPU faiss.
RUN poetry install --only main --extras faiss-gpu --no-interaction --no-ansi

# Fail the BUILD (not the GPU job) if deps didn't land in the runtime env.
RUN python -c "import numpy, torch, transformers; print('deps ok:', torch.__version__)"

# Default command = build the graph index (NER + OpenIE extraction).
# Override args via the job (dataset, backend, model).
ENTRYPOINT ["python", "-m", "gfmrag.workflow.index_dataset"]
