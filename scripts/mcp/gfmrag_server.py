"""MCP server exposing the GFM-RAG knowledge graph (G-Reasoner) as tools.

Any MCP client (Claude Code, Claude Desktop, Managed Agents, etc.) can use the
graph as a retriever. The server proxies to the Cloud Run QA service, minting an
IAM ID token via gcloud (the service is private). Stdio transport.

The QA service serves ONE dataset at a time (its DATA_NAME env). Point it at the
shard you want; this server just calls /retrieve, /answer, /ready.

Env overrides: GFMRAG_QA_URL, GFMRAG_SA, GFMRAG_DATASET (label only).
"""
import json
import os
import subprocess
import time
import urllib.request

from mcp.server.fastmcp import FastMCP

SA = os.environ.get("GFMRAG_SA",
                    "gfmrag-terraform@tautsec-graph-crawler.iam.gserviceaccount.com")
QA = os.environ.get("GFMRAG_QA_URL", "https://gfmrag-qa-olbu7sektq-uc.a.run.app")
DATASET = os.environ.get("GFMRAG_DATASET", "shard-4")  # which index the service serves

mcp = FastMCP("gfmrag")

_tok = {"v": None, "exp": 0.0}


def _token() -> str:
    """Mint/cache an IAM ID token for the private QA service (valid ~60m)."""
    if _tok["v"] and time.time() < _tok["exp"]:
        return _tok["v"]
    t = subprocess.check_output(
        ["gcloud", "auth", "print-identity-token", "--account", SA, "--audiences", QA],
        text=True).strip()
    _tok["v"], _tok["exp"] = t, time.time() + 45 * 60
    return t


def _post(path: str, payload: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(
        QA + path, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


@mcp.tool()
def gfm_retrieve(query: str, top_k: int = 8,
                 target_types: list[str] | None = None) -> str:
    """Retrieve from the GFM-RAG knowledge graph via semantic + multi-hop graph
    reasoning (G-Reasoner GNN over the Australian Modern Slavery Register).

    Returns ranked nodes with scores and text. Use target_types=["document"] for
    statement passages (best grounding for an answer); ["entity"] for company /
    ABN / sector entities. Issue follow-up retrievals to trace relationships
    (joint filings, group structure) — that is the graph's multi-hop strength.
    Call gfm_status to see which dataset (shard) the service is serving.
    """
    types = target_types or ["document"]
    res = _post("/retrieve", {"query": query, "top_k": top_k, "target_types": types})
    blocks = []
    for t, items in res.items():
        if not isinstance(items, list):
            continue
        lines = [f"## {t} (top {len(items)})"]
        for it in items:
            lines.append(f"[{it.get('score', 0):+.2f}] {it.get('id')}")
            attrs = it.get("attributes")
            if attrs:
                lines.append(f"    {str(attrs)[:600]}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) if blocks else "(no results)"


@mcp.tool()
def gfm_answer(query: str, top_k: int = 6) -> str:
    """Ask the GFM-RAG service a question: it retrieves statements from the graph
    and synthesizes a natural-language answer with the server-side LLM. Slower
    than gfm_retrieve (LLM generation). Call gfm_status for the active dataset.
    """
    res = _post("/answer", {"query": query, "top_k": top_k, "target_types": ["document"]},
                timeout=600)
    return res.get("answer", "(no answer)")


@mcp.tool()
def gfm_status() -> str:
    """Check GFM-RAG service readiness (loading / warming / ready) and which dataset
    it serves. Call before querying after the service has been idle (it scales to
    zero and cold-starts; the first query builds the ColBERT index and is slow)."""
    try:
        req = urllib.request.Request(QA + "/ready",
                                     headers={"Authorization": f"Bearer {_token()}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.load(r)
        body["configured_dataset"] = DATASET
        return json.dumps(body)
    except Exception as e:  # noqa: BLE001
        return f"status error: {e}"


if __name__ == "__main__":
    mcp.run()
