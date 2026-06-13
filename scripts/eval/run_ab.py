"""A/B over the 0-5 union: GRAPH (GFM-RAG /retrieve) vs FLAT (cosine top-k over
the SAME document embeddings from graph.pt, same Qwen3-Embedding space). Only
the retrieval algorithm differs."""
import os
os.environ["CUDA_VISIBLE_DEVICES"] = ""  # local GPU (Maxwell) has no usable CUDA kernels; force CPU
import json, subprocess, sys, urllib.request
import torch
import torch.nn.functional as F

FP = "71345f28ce99ab5be49b591c8c642cc6"
SA = "gfmrag-terraform@tautsec-graph-crawler.iam.gserviceaccount.com"
QA = "https://gfmrag-qa-olbu7sektq-uc.a.run.app"
BASE = f"corpus-shards/union-0-5/processed/stage2/{FP}"

# --- FLAT baseline: document-node embeddings straight from graph.pt ---
g = torch.load(f"{BASE}/graph.pt", weights_only=False, map_location="cpu")
doc_ids = g["nodes_by_type"]["document"]
doc_ids = doc_ids.tolist() if hasattr(doc_ids, "tolist") else list(doc_ids)
doc_emb = F.normalize(g["x"][doc_ids].float(), dim=1)            # [17090,1024]
n2i = json.load(open(f"{BASE}/node2id.json"))
i2n = {v: k for k, v in n2i.items()}
doc_names = [i2n[i] for i in doc_ids]
print(f"flat index: {doc_emb.shape[0]} document embeddings", file=sys.stderr)

from gfmrag.text_emb_models import Qwen3TextEmbModel
qm = Qwen3TextEmbModel(
    "Qwen/Qwen3-Embedding-0.6B", normalize=True,
    query_instruct="Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery: ",
    truncate_dim=1024)

def flat(q, k=8):
    qv = F.normalize(qm.encode([q], is_query=True, show_progress_bar=False)[0].float(), dim=0)
    s = doc_emb @ qv
    top = torch.topk(s, k)
    return [(doc_names[i], float(s[i])) for i in top.indices.tolist()]

tok = subprocess.check_output(
    ["gcloud", "auth", "print-identity-token", "--account", SA, "--audiences", QA], text=True).strip()

def graph(q, k=8, timeout=900):  # first call may absorb a cold-start ColBERT rebuild (~14min)
    body = json.dumps({"query": q, "top_k": k, "target_types": ["document"]}).encode()
    req = urllib.request.Request(QA + "/retrieve", data=body,
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.load(r)
    return [(d["id"], d["score"]) for d in resp.get("document", [])[:k]]

def short(t, n=44):
    t = str(t).split(":", 1)[-1].strip()
    return (t[:n] + "…") if len(t) > n else t

QUERIES = [
    ("A multi-hop", "companies that filed a joint modern slavery statement together with a mining or resources company"),
    ("A multi-hop", "entities included within a parent company's group modern slavery statement"),
    ("A multi-hop", "joint statements filed by a group of related subsidiary companies"),
    ("B segment",   "financial, insurance and real estate companies that filed statements"),
    ("B segment",   "reporting entities with annual revenue of one billion dollars or more"),
    ("C lead",      "large Australian retail and consumer goods companies"),
    ("C lead",      "food, beverage and agriculture companies that source goods internationally"),
    ("D crawl",     "importers and logistics companies whose supply chains span multiple countries"),
    ("D crawl",     "textiles, apparel and consumer goods companies in high modern slavery risk sectors"),
    ("D crawl",     "large mining and resources entities suitable for supplier mapping"),
    ("control",     "what is the ABN of IKEA Pty Limited"),
    ("B segment",   "reporting entities headquartered in the United States"),
]
out = []
for cat, q in QUERIES:
    A, B = graph(q), flat(q)
    overlap = len(set(n for n, _ in A[:5]) & set(n for n, _ in B[:5]))
    print(f"\n[{cat}] {q}  (top-5 overlap: {overlap}/5)")
    print("  GRAPH: " + " | ".join(short(n) for n, _ in A[:5]))
    print("  FLAT : " + " | ".join(short(n) for n, _ in B[:5]))
    out.append({"cat": cat, "q": q, "overlap_top5": overlap,
                "graph": [n for n, _ in A], "flat": [n for n, _ in B]})
json.dump(out, open("tmp/ab-union-results.json", "w"), indent=2)
print("\nwrote tmp/ab-union-results.json")
