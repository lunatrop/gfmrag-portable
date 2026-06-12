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

def answer(tok, query):
    body = json.dumps({"query": query, "top_k": 6, "target_types": ["document"]}).encode()
    req = urllib.request.Request(QA + "/answer", data=body,
                                 headers={"Authorization": f"Bearer {tok}",
                                          "Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        resp = json.load(r)
    return time.time() - t0, resp

tok = token()
for i, (cat, q) in enumerate(DEMOS, 1):
    try:
        secs, resp = answer(tok, q)
    except Exception as e:
        print(f"\n[{i}] {cat} ERROR: {e}\n  Q: {q}")
        continue
    docs = resp.get("retrieved", {}).get("document", [])
    print(f"\n========== DEMO {i} [{cat}]  ({secs:.1f}s) ==========")
    print(f"Q: {q}")
    print(f"\nANSWER:\n{resp.get('answer','(none)')}")
    print(f"\n(grounded on {len(docs)} retrieved statements; top: "
          + "; ".join(str(d['id']).split(':',1)[-1].strip()[:32] for d in docs[:3]) + ")")
