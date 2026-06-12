"""Run 12 sophisticated queries against shard-4 via the QA /retrieve endpoint.

Measures per-query latency and captures top entity + document hits so retrieval
quality can be judged. Queries span four capability axes:
  A. multi-hop / relational reasoning   (joint filings, group structure, joins)
  B. segment aggregation                (sector / revenue / geography slices)
  C. marketing leads                    (ICP targeting for compliance/SaaS)
  D. supply-chain crawler seeding       (which ABNs to crawl, risk-prioritised)
"""
import json, subprocess, time, urllib.request

SA = "gfmrag-terraform@tautsec-graph-crawler.iam.gserviceaccount.com"
QA = "https://gfmrag-qa-olbu7sektq-uc.a.run.app"
TOP_K = 8

QUERIES = [
    ("A multi-hop", "Companies that filed a joint modern slavery statement together with another reporting entity"),
    ("A multi-hop", "Subsidiaries and entities included within a parent company's group modern slavery statement"),
    ("A multi-hop", "Mining, metals and resources companies that are headquartered outside Australia"),
    ("B segment",   "Financial, insurance and real estate companies that filed modern slavery statements"),
    ("B segment",   "Reporting entities with annual revenue of one billion dollars or more"),
    ("B segment",   "Reporting entities headquartered in the United States"),
    ("C lead",      "Large Australian retail and consumer goods companies that are prospects for modern slavery compliance software"),
    ("C lead",      "High revenue manufacturing and industrial companies with complex global operations"),
    ("C lead",      "Food, beverage and agriculture companies that source goods internationally"),
    ("D crawl",     "Importers and logistics companies whose supply chains span multiple countries"),
    ("D crawl",     "Textiles, apparel and consumer goods companies in high modern slavery risk sectors to map suppliers for"),
    ("D crawl",     "Large mining and resources entities suitable for tier-one supplier mapping and ABN enrichment"),
]


def token():
    return subprocess.check_output(
        ["gcloud", "auth", "print-identity-token", "--account", SA, "--audiences", QA],
        text=True).strip()


def retrieve(tok, query):
    body = json.dumps({"query": query, "top_k": TOP_K,
                       "target_types": ["entity", "document"]}).encode()
    req = urllib.request.Request(QA + "/retrieve", data=body,
                                 headers={"Authorization": f"Bearer {tok}",
                                          "Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=180) as r:
        resp = json.load(r)
    return time.time() - t0, resp


def short(s, n=58):
    return (s[:n] + "…") if len(s) > n else s


def main():
    tok = token()
    out, lats = [], []
    for i, (cat, q) in enumerate(QUERIES, 1):
        try:
            secs, resp = retrieve(tok, q)
        except Exception as e:
            print(f"\n[{i:>2}] {cat}  ERROR: {e}\n  Q: {q}")
            out.append({"i": i, "cat": cat, "q": q, "error": str(e)})
            continue
        lats.append(secs)
        ents = resp.get("entity", [])
        docs = resp.get("document", [])
        print(f"\n[{i:>2}] {cat}  ({secs:.2f}s)\n  Q: {q}")
        print("  top entities:")
        for e in ents[:6]:
            print(f"     {e['score']:+.2f}  {short(str(e['id']))}")
        print("  top statements:")
        for d in docs[:3]:
            print(f"     {d['score']:+.2f}  {short(str(d['id']), 70)}")
        out.append({"i": i, "cat": cat, "q": q, "secs": round(secs, 3),
                    "entities": [{"id": e["id"], "score": e["score"]} for e in ents],
                    "documents": [{"id": d["id"], "score": d["score"]} for d in docs]})

    json.dump(out, open("tmp/query-results.json", "w"), indent=2)
    if lats:
        lats_s = sorted(lats)
        n = len(lats_s)
        print("\n=== LATENCY (per-query /retrieve, warm) ===")
        print(f"  n={n}  mean={sum(lats_s)/n:.2f}s  median={lats_s[n//2]:.2f}s "
              f"min={lats_s[0]:.2f}s  max={lats_s[-1]:.2f}s  p90={lats_s[int(n*0.9)-1]:.2f}s")


if __name__ == "__main__":
    main()
