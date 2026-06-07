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
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

DATA_DIR = os.environ.get("DATA_DIR", "/data")
DATA_NAME = os.environ.get("DATA_NAME", "mycorpus")
GFM_MODEL_PATH = os.environ.get("GFM_MODEL_PATH", "rmanluo/GFM-RAG-8M")
LLM_API = os.environ.get("LLM_API", "openai")
LLM_MODEL = os.environ.get("LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")
EL_MODEL = os.environ.get("EL_MODEL", "colbert-ir/colbertv2.0")
DEFAULT_TOP_K = int(os.environ.get("TOP_K", "5"))

_state: dict = {"retriever": None, "llm": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Heavy imports + model/index load happen once at startup.
    from gfmrag import GFMRetriever
    from gfmrag.graph_index_construction.entity_linking_model import ColbertELModel
    from gfmrag.graph_index_construction.ner_model import LLMNERModel

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


@app.get("/healthz")
def healthz() -> dict:
    # Readiness probe gates traffic until the model + index are loaded.
    return {"status": "ok" if _state["retriever"] is not None else "loading"}


@app.post("/retrieve")
def retrieve(q: Query) -> dict:
    """Graph retrieval over the KG: returns top-k nodes per target type."""
    retriever = _state["retriever"]
    if retriever is None:
        return {"error": "model still loading"}
    return retriever.retrieve(
        q.query, top_k=q.top_k or DEFAULT_TOP_K, target_types=q.target_types
    )


@app.post("/answer")
def answer(q: Query) -> dict:
    """Retrieve + generate an answer with the LLM (vLLM).

    Uses a minimal generic prompt. For dataset-specific prompting, swap in
    gfmrag.prompt_builder.QAPromptBuilder (as the qa workflow does).
    """
    retriever = _state["retriever"]
    if retriever is None:
        return {"error": "model still loading"}

    docs = retriever.retrieve(
        q.query, top_k=q.top_k or DEFAULT_TOP_K, target_types=q.target_types
    )

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
