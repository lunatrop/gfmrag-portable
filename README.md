# tautsec-gfm-service

A thin **MCP client** that exposes the TautSec GFM-RAG knowledge graph (the
Australian Modern Slavery Register supply-chain graph, served by G-Reasoner on
Cloud Run) to **Claude Code** and **Claude Desktop**.

This repo is intentionally small: it contains only a proxy that calls the hosted
service. No models, no graph, no GPU — all compute is the shared Cloud Run
service. (A fully-local engine is a planned **advanced** option, not included
here.)

## Tools

| Tool | What it does |
|------|--------------|
| `gfm_retrieve(query, top_k, target_types)` | Graph retrieval over the KG. Defaults to `["document"]`; `["entity"]` available but degraded. |
| `gfm_answer(query, top_k)` | Retrieve + server-side LLM answer. Slower. |
| `gfm_status()` | Service readiness (loading / warming / ready) + active dataset. Call this first after idle. |

## Prerequisites

- Python 3.10+
- `gcloud` CLI on PATH
- A `@tautsec.com` Google account with **`roles/run.invoker`** on the `gfmrag-qa`
  service (ask an admin to grant it once).

## Install (Claude Code)

```bash
git clone <this-repo> tautsec-gfm-service
cd tautsec-gfm-service
pip install -r requirements.txt          # just the `mcp` package
gcloud auth login you@tautsec.com         # identity used to mint the service token
```

Open Claude Code in this directory — it auto-discovers `.mcp.json`, launches the
`gfmrag` server, and the three tools appear (approve the project MCP server on
first prompt). Or register it explicitly:

```bash
claude mcp add gfmrag -- python scripts/mcp/gfmrag_server.py
```

**Claude Desktop:** add the same block from `.mcp.json` to
`claude_desktop_config.json`. **Windows users** run the server through WSL —
set the command to `wsl.exe` with args `-d ubuntu bash -c "python
$(pwd)/scripts/mcp/gfmrag_server.py"` (gcloud + the `mcp` package must be in WSL).

## How access works

The service is private. The proxy mints a short-lived Google **ID token** via
`gcloud auth print-identity-token` (cached ~45 min) and sends it as a Bearer
token. Your own Google identity is the auth — no shared keys. Missing
`run.invoker` → HTTP 403.

## Cold starts

The service scales to zero. After idle, the first query triggers a multi-minute
cold start (model load + ColBERT index build). Call `gfm_status` first; if it is
not `ready`, it is warming — wait, don't hammer it.

## Config (env in `.mcp.json`)

| Var | Default | Purpose |
|-----|---------|---------|
| `GFMRAG_QA_URL` | the deployed service URL | which service to call |
| `GFMRAG_SA` | the runtime SA | token audience account |
| `GFMRAG_DATASET` | label only | informational; `gfm_status` reports the real served dataset |

---
*Replication source: this branch (`tautsec-gfm-service`) of the gfm-rag engine
repo is the seed for the standalone `tautsec-gfm-service` repository. Copy these
files into a fresh-history repo — do not fork the engine's history.*
