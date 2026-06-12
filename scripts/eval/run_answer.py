"""Demo the /answer endpoint: retrieve statements + LLM (Qwen2.5-3B) synthesis."""
import json, subprocess, time, urllib.request

SA = "gfmrag-terraform@tautsec-graph-crawler.iam.gserviceaccount.com"
QA = "https://gfmrag-qa-olbu7sektq-uc.a.run.app"

DEMOS = [
    ("C lead",      "Which food, beverage and agriculture companies source goods internationally? List them with their ABN."),
    ("D crawl",     "Which importers or logistics companies have supply chains spanning multiple countries, and what sectors are they in?"),
    ("A multi-hop", "Which entities filed as part of a parent company's group or joint modern slavery statement?"),
]

def token():
    return subprocess.check_output(
        ["gcloud", "auth", "print-identity-token", "--account", SA, "--audiences", QA],
        text=True).strip()

OUT = "corpus-tuples/shard4-answer-demos.json"

def answer(tok, query, timeout=900):
    body = json.dumps({"query": query, "top_k": 6, "target_types": ["document"]}).encode()
    req = urllib.request.Request(QA + "/answer", data=body,
                                 headers={"Authorization": f"Bearer {tok}",
                                          "Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.load(r)
    return time.time() - t0, resp

tok = token()
# Warm the vLLM (Qwen2.5-3B) generation service first so the first timed demo
# doesn't eat a cold start (observed: first /answer timed out otherwise).
try:
    print("warming vLLM via a throwaway /answer ...")
    answer(tok, "warmup", timeout=900)
except Exception as e:
    print(f"(warmup call returned: {e})")

results = []
for i, (cat, q) in enumerate(DEMOS, 1):
    try:
        secs, resp = answer(tok, q)
    except Exception as e:
        print(f"\n[{i}] {cat} ERROR: {e}\n  Q: {q}")
        results.append({"i": i, "cat": cat, "q": q, "error": str(e)})
        continue
    docs = resp.get("retrieved", {}).get("document", [])
    ans = resp.get("answer", "(none)")
    print(f"\n========== DEMO {i} [{cat}]  ({secs:.1f}s) ==========")
    print(f"Q: {q}")
    print(f"\nANSWER:\n{ans}")
    print(f"\n(grounded on {len(docs)} retrieved statements; top: "
          + "; ".join(str(d['id']).split(':',1)[-1].strip()[:32] for d in docs[:3]) + ")")
    results.append({"i": i, "cat": cat, "q": q, "secs": round(secs, 1), "answer": ans,
                    "grounded_on": [str(d["id"]) for d in docs]})

json.dump(results, open(OUT, "w"), indent=2)
print(f"\nwrote {OUT}")
