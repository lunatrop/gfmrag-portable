"""Method-3 merge of shard-5's 17 sub-shards (s5-0..16) into one stage-1 dataset.
Same logic as the shard-4 merge: concat the stage-1 tuple CSVs + documents,
dedup nodes/relations by name and edges by (source,relation,target)."""
import json
import os
import pandas as pd

SUBSHARDS = [f"s5-{i}" for i in range(17)]
TUPLES = "corpus-tuples"           # stage-1 CSVs per sub-shard (downloaded by the campaign)
DOCS = "corpus-campaign5"          # raw/documents.json per sub-shard (from staging)
OUT = "corpus-shards/shard-5"

os.makedirs(f"{OUT}/raw", exist_ok=True)
os.makedirs(f"{OUT}/processed/stage1", exist_ok=True)


def load_docs(s):
    d = json.load(open(f"{DOCS}/{s}/raw/documents.json"))
    if isinstance(d, list):
        d = {x.get("title", x.get("id", str(i))): x.get("content", x.get("text", ""))
             for i, x in enumerate(d)}
    return d


# --- documents.json: union of {title: content} ---
docs, dup_docs = {}, 0
for s in SUBSHARDS:
    for k, v in load_docs(s).items():
        if k in docs:
            dup_docs += 1
        docs[k] = v
json.dump(docs, open(f"{OUT}/raw/documents.json", "w"), ensure_ascii=False)

# --- nodes.csv: dedup by name ---
nodes = pd.concat([pd.read_csv(f"{TUPLES}/{s}/nodes.csv", keep_default_na=False)
                   for s in SUBSHARDS], ignore_index=True)
n_nodes_raw = len(nodes)
nodes = nodes.drop_duplicates(subset=["name"], keep="first")
nodes.to_csv(f"{OUT}/processed/stage1/nodes.csv", index=False)
node_names = set(nodes["name"])
del nodes

# --- relations.csv: dedup by name ---
rels = pd.concat([pd.read_csv(f"{TUPLES}/{s}/relations.csv", keep_default_na=False)
                  for s in SUBSHARDS], ignore_index=True)
n_rels_raw = len(rels)
rels = rels.drop_duplicates(subset=["name"], keep="first")
rels.to_csv(f"{OUT}/processed/stage1/relations.csv", index=False)
n_rels = len(rels)
del rels

# --- edges.csv: dedup by (source, relation, target) ---
edges = pd.concat([pd.read_csv(f"{TUPLES}/{s}/edges.csv", keep_default_na=False)
                   for s in SUBSHARDS], ignore_index=True)
n_edges_raw = len(edges)
edges = edges.drop_duplicates(subset=["source", "relation", "target"], keep="first")
n_edges = len(edges)
missing = (~edges["source"].isin(node_names)).sum() + (~edges["target"].isin(node_names)).sum()
edges.to_csv(f"{OUT}/processed/stage1/edges.csv", index=False)

print("=== shard-5 method-3 merge ===")
print(f"documents : {len(docs):>8}  ({dup_docs} dup titles collapsed)")
print(f"nodes     : {n_nodes_raw:>8} -> {len(node_names):>8}  ({n_nodes_raw-len(node_names)} dups removed)")
print(f"relations : {n_rels_raw:>8} -> {n_rels:>8}  ({n_rels_raw-n_rels} dups removed)")
print(f"edges     : {n_edges_raw:>8} -> {n_edges:>8}  ({n_edges_raw-n_edges} dups removed)")
print(f"edge endpoints missing from nodes: {missing} (0 expected)")
