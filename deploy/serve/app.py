"""FastAPI prompting service over a gfmrag knowledge graph.

Loads a GFM checkpoint (e.g. ``rmanluo/GFM-RAG-8M`` or the 34M G-Reasoner) plus
the KG index produced by the extractor, and serves graph retrieval (+ an optional
LLM-generated answer). Query-NER and answer generation are routed to the
in-cluster vLLM via the OpenAI-compatible API.

Env:
  DATA_DIR        index root mounted from GCS         (default /data)
  DATA_NAME       dataset subdirectory                (default mycorpus)
  GFM_MODEL_PATH  HF id or local path                 (default rmanluo/GFM-RAG-8M)
  LLM_API         backend for NER + answer            (default openai -> vLLM)
  LLM_MODEL       model name served by the backend    (default Qwen/Qwen2.5-7B-Instruct)
  OPENAI_BASE_URL vLLM endpoint (set by the Deployment)
  EL_MODEL        ColBERT checkpoint                  (default colbert-ir/colbertv2.0)
  TOP_K           default results per type            (default 5)
"""

import os
import time
import urllib.request
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

DATA_DIR = os.environ.get("DATA_DIR", "/data")
DATA_NAME = os.environ.get("DATA_NAME", "mycorpus")
GFM_MODEL_PATH = os.environ.get("GFM_MODEL_PATH", "rmanluo/GFM-RAG-8M")
LLM_API = os.environ.get("LLM_API", "openai")
LLM_MODEL = os.environ.get("LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")
EL_MODEL = os.environ.get("EL_MODEL", "colbert-ir/colbertv2.0")
DEFAULT_TOP_K = int(os.environ.get("TOP_K", "5"))

# On Cloud Run, vLLM sits behind IAM: every request must carry a Google ID
# token for the vLLM service. Set VLLM_AUDIENCE to the service URL to enable;
# unset (GKE / local, where the endpoint is unauthenticated) this is a no-op.
VLLM_AUDIENCE = os.environ.get("VLLM_AUDIENCE", "")

# "warm" tracks the third readiness layer: the first /retrieve on a fresh
# instance triggers ColBERT PLAID index build + first GPU embedding pass
# (tens of seconds to minutes). Until that has run once, the service is
# "warming" — loaded but not yet at steady-state latency.
_state: dict = {"retriever": None, "llm": None, "warm": False}
_token: dict = {"expires": 0.0}


def _refresh_openai_token() -> None:
    """Mint a fresh ID token for vLLM and push it into the cached clients.

    ID tokens live 60 minutes; refresh after 45. The metadata server is only
    reachable on GCP — hence gated on VLLM_AUDIENCE.
    """
    if not VLLM_AUDIENCE or time.time() < _token["expires"]:
        return
    req = urllib.request.Request(
        "http://metadata.google.internal/computeMetadata/v1/instance/"
        f"service-accounts/default/identity?audience={VLLM_AUDIENCE}",
        headers={"Metadata-Flavor": "Google"},
    )
    tok = urllib.request.urlopen(req, timeout=10).read().decode()
    _token["expires"] = time.time() + 45 * 60

    # New clients pick the token up from the env; existing ones cached it at
    # construction and are updated in place.
    os.environ["OPENAI_API_KEY"] = tok
    if _state["llm"] is not None:
        _state["llm"].client.api_key = tok  # gfmrag.llms.ChatGPT
    retriever = _state["retriever"]
    if retriever is not None:
        # LLMNERModel.client is a langchain ChatOpenAI wrapping an OpenAI client.
        root_client = getattr(retriever.ner_model.client, "root_client", None)
        if root_client is not None:
            root_client.api_key = tok


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Heavy imports + model/index load happen once at startup.
    from gfmrag import GFMRetriever
    from gfmrag.graph_index_construction.entity_linking_model import ColbertELModel
    from gfmrag.graph_index_construction.ner_model import LLMNERModel

    _refresh_openai_token()  # before any client caches OPENAI_API_KEY
    ner_model = LLMNERModel(llm_api=LLM_API, model_name=LLM_MODEL)
    el_model = ColbertELModel(model_name_or_path=EL_MODEL, root="/tmp/colbert")

    _state["retriever"] = GFMRetriever.from_index(
        data_dir=DATA_DIR,
        data_name=DATA_NAME,
        model_path=GFM_MODEL_PATH,  # 8M or 34M checkpoint, pulled from HF
        ner_model=ner_model,
        el_model=el_model,
    )
    yield
    _state["retriever"] = None


app = FastAPI(title="gfmrag prompting service", lifespan=lifespan)


class Query(BaseModel):
    query: str
    top_k: int | None = None
    target_types: list[str] | None = None


def _readiness() -> dict:
    """Three-layer readiness, with a human message for each state.

    loading  — lifespan still loading the GFM checkpoint + index
    warming  — loaded, but the first (lazy-init) retrieval hasn't run; the
               next /retrieve|/answer will be slow (ColBERT/embedding build)
    ready    — a retrieval has completed; steady-state latency (~1s)
    """
    if _state["retriever"] is None:
        return {"state": "loading", "ready": False,
                "detail": "GFM checkpoint + KG index still loading"}
    if not _state["warm"]:
        return {"state": "warming", "ready": False,
                "detail": "models loaded; first query runs lazy init "
                          "(ColBERT index + GPU embedding pass) and will be slow"}
    return {"state": "ready", "ready": True, "detail": "steady-state"}


# /healthz is 404'd by the Cloud Run layer (it's the startup-probe path); /ready
# is the externally reachable readiness endpoint. Both are served by the app.
@app.get("/healthz")
@app.get("/ready")
def ready() -> JSONResponse:
    r = _readiness()
    # 503 while loading so callers/probes can poll; 200 once it's at least loaded.
    return JSONResponse(r, status_code=200 if _state["retriever"] is not None else 503)


@app.post("/warmup")
def warmup() -> dict:
    """Run a priming retrieval to absorb lazy init, so the next real query is
    fast. Idempotent. The benchmarking app should call this (and poll /ready)
    before issuing user queries, surfacing 'warming up…' meanwhile."""
    retriever = _state["retriever"]
    if retriever is None:
        return {"state": "loading", "warmed": False}
    _refresh_openai_token()
    t0 = time.time()
    retriever.retrieve("warmup probe", top_k=1)
    _state["warm"] = True
    return {"state": "ready", "warmed": True, "warmup_secs": round(time.time() - t0, 1)}


@app.post("/retrieve")
def retrieve(q: Query) -> dict:
    """Graph retrieval over the KG: returns top-k nodes per target type."""
    retriever = _state["retriever"]
    if retriever is None:
        return {"error": "model still loading", "state": "loading"}
    _refresh_openai_token()
    result = retriever.retrieve(
        q.query, top_k=q.top_k or DEFAULT_TOP_K, target_types=q.target_types
    )
    _state["warm"] = True  # warm-state is reported via /ready, not by reshaping this response
    return result


@app.post("/answer")
def answer(q: Query) -> dict:
    """Retrieve + generate an answer with the LLM (vLLM).

    Uses a minimal generic prompt. For dataset-specific prompting, swap in
    gfmrag.prompt_builder.QAPromptBuilder (as the qa workflow does).
    """
    retriever = _state["retriever"]
    if retriever is None:
        return {"error": "model still loading"}

    _refresh_openai_token()
    docs = retriever.retrieve(
        q.query, top_k=q.top_k or DEFAULT_TOP_K, target_types=q.target_types
    )
    _state["warm"] = True

    if _state["llm"] is None:
        from gfmrag.llms import ChatGPT

        _state["llm"] = ChatGPT(model_name_or_path=LLM_MODEL)

    context = "\n".join(
        f"- {item.get('attributes', item)}"
        for items in docs.values()
        for item in items
    )
    prompt = (
        "Answer the question using only the context below.\n\n"
        f"Context:\n{context}\n\nQuestion: {q.query}\nAnswer:"
    )
    response = _state["llm"].generate_sentence(prompt)
    return {"query": q.query, "answer": response, "retrieved": docs}
