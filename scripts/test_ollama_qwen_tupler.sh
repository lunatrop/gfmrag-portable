#!/usr/bin/env bash
#
# test_ollama_qwen_tupler.sh
#
# Starts the Ollama server if it isn't already running, makes sure the model is
# available, then runs the OpenIE tuple extractor against a sample passage and
# prints the extracted entities and (subject, relation, object) triples.
#
# Usage:
#   ./scripts/test_ollama_qwen_tupler.sh ["a passage to extract from"]
#
# Environment overrides:
#   OLLAMA_HOST    host:port of the server   (default 127.0.0.1:11434)
#   OLLAMA_MODEL   model to use              (default qwen2.5:3b)
#   PYTHON         python interpreter        (default <repo>/.venv/bin/python)

set -euo pipefail

# --- locate repo root relative to this script ---------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# --- config -------------------------------------------------------------------
export PATH="$HOME/.local/bin:$PATH"
export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
MODEL="${OLLAMA_MODEL:-qwen2.5:3b}"
PY="${PYTHON:-$REPO_ROOT/.venv/bin/python}"
BASE_URL="http://${OLLAMA_HOST}"
PASSAGE="${1:-Clarence Fred Gehrke (1918-2002) was an American football player. He designed the Los Angeles Rams logo in 1948.}"

log()  { printf '\n\033[1;34m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
fail() { printf '\n\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

server_up() { curl -sf -m 2 "$BASE_URL/api/tags" >/dev/null 2>&1; }

# --- 1. prerequisites ---------------------------------------------------------
command -v ollama >/dev/null 2>&1 || fail "ollama not found on PATH (expected in ~/.local/bin)."
command -v curl   >/dev/null 2>&1 || fail "curl is required but not found."
[ -x "$PY" ]                      || fail "venv python not found at $PY — run 'poetry install' first."

# --- 2. start the server if needed --------------------------------------------
if server_up; then
    log "Ollama server already running at $BASE_URL"
else
    log "Ollama server not running — starting it (logs: /tmp/ollama_serve.log)..."
    nohup ollama serve >/tmp/ollama_serve.log 2>&1 &
    log "Launched 'ollama serve' (pid $!). Waiting for it to become ready..."
    for i in $(seq 1 60); do
        if server_up; then
            log "Server is up."
            break
        fi
        printf '.'
        sleep 1
        [ "$i" -eq 60 ] && fail "server did not become ready within 60s (see /tmp/ollama_serve.log)."
    done
fi

# --- 3. make sure the model is available --------------------------------------
if ollama list | awk 'NR>1 {print $1}' | grep -qx "$MODEL"; then
    log "Model '$MODEL' is available."
else
    log "Model '$MODEL' not found — pulling it now (this can take a while)..."
    ollama pull "$MODEL"
fi

# --- 4. run the extractor -----------------------------------------------------
log "Running tuple extractor with model '$MODEL'"
log "Passage: $PASSAGE"

OLLAMA_MODEL="$MODEL" PASSAGE="$PASSAGE" "$PY" - <<'PY'
import os, sys, time

print("  -> importing gfmrag and instantiating the OpenIE model...", flush=True)
from hydra.utils import instantiate
from omegaconf import OmegaConf

model = os.environ["OLLAMA_MODEL"]
passage = os.environ["PASSAGE"]

cfg = OmegaConf.create({
    "_target_": "gfmrag.graph_index_construction.openie_model.LLMOPENIEModel",
    "llm_api": "ollama",
    "model_name": model,
})
extractor = instantiate(cfg)

print("  -> running NER + OpenIE (may take ~30s-3min on a small GPU)...", flush=True)
t0 = time.time()
res = extractor(passage)
dt = time.time() - t0
print(f"  -> extraction finished in {dt:.1f}s", flush=True)

print("\nENTITIES (%d):" % len(res["extracted_entities"]))
for e in res["extracted_entities"]:
    print("  -", e)

print("\nTRIPLES (%d):" % len(res["extracted_triples"]))
for s, p, o in res["extracted_triples"]:
    print(f"  ({s}) --[{p}]--> ({o})")

if not res["extracted_entities"] or not res["extracted_triples"]:
    print("\nWARNING: extractor returned empty entities or triples.", file=sys.stderr)
    sys.exit(1)
PY

log "Done."
