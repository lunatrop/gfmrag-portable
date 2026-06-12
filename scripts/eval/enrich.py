"""Turn retrieved statements into lead/crawler-seed cards: for each query's top
documents, resolve the reporting company and look up its ABN, sector, revenue
band and HQ from the graph. This is the concrete artifact a marketing list or a
supply-chain crawler would consume."""
import json, re, pandas as pd, collections

base = "corpus-shards/shard-4/processed/stage1"
edges = pd.read_csv(f"{base}/edges.csv", keep_default_na=False)

# index: source entity -> {relation -> [targets]}
by_src = collections.defaultdict(lambda: collections.defaultdict(list))
for s, r, t in zip(edges["source"], edges["relation"], edges["target"]):
    by_src[s][r].append(t)

ABN_RE = re.compile(r"^\d[\d ]{8,}$")
def meta(company):
    e = by_src.get(company, {})
    def first(*rels):
        for r in rels:
            if e.get(r):
                return e[r][0]
        return "—"
    return {
        "abn": first("has abn", "has a b n"),
        "sector": first("operates in sector", "received sector", "registered sector"),
        "revenue": first("has annual revenue band", "annual revenue band", "received annual revenue band", "registered revenue band"),
        "hq": first("headquartered in", "is headquartered in", "received headquartered in"),
    }

def company_from_title(title):
    # "Modern slavery statement 2021-590: THE REJECT SHOP LIMITED" -> entity name
    m = re.search(r":\s*(.+)$", title)
    name = (m.group(1) if m else title).strip().lower()
    name = name.split(",")[0].split(" & ")[0].strip()  # first named entity for joints
    # entity names in the graph collapse punctuation to spaces
    return re.sub(r"[^a-z0-9]+", " ", name).strip()

res = json.load(open("tmp/query-results.json"))
for q in res:
    if "documents" not in q:
        continue
    print(f"\n[{q['i']:>2}] {q['cat']}: {q['q']}")
    for d in q["documents"][:4]:
        title = str(d["id"])
        comp = company_from_title(title)
        m = meta(comp)
        label = title.split(":", 1)[-1].strip()[:46]
        print(f"   • {label:<46} ABN {m['abn']:<14} rev {m['revenue']:<10} hq {m['hq'][:18]:<18} | {m['sector'][:40]}")
