"""Method-3 union of all 6 top-level shards (0-5) into one stage-1 dataset.
Concat each shard's stage-1 tuple CSVs + documents; dedup nodes/relations by
name, edges by (source,relation,target). This is the cross-shard merge that
feeds the single union stage-2 build."""
import json
import os
import pandas as pd

SHARDS = [
    ("shard-0", "corpus-union/shard-0"),
    ("shard-1", "corpus-union/shard-1"),
    ("shard-2", "corpus-union/shard-2"),
    ("shard-3", "corpus-union/shard-3"),
    ("shard-4", "corpus-shards/shard-4"),
    ("shard-5", "corpus-shards/shard-5"),
]
OUT = "corpus-shards/union-0-5"
os.makedirs(f"{OUT}/raw", exist_ok=True)
os.makedirs(f"{OUT}/processed/stage1", exist_ok=True)


def docs_of(root):
    d = json.load(open(f"{root}/raw/documents.json"))
    if isinstance(d, list):
        d = {x.get("title", x.get("id", str(i))): x.get("content", x.get("text", ""))
             for i, x in enumerate(d)}
    return d


# documents
docs, dup_docs = {}, 0
for name, root in SHARDS:
    for k, v in docs_of(root).items():
        if k in docs:
            dup_docs += 1
        docs[k] = v
json.dump(docs, open(f"{OUT}/raw/documents.json", "w"), ensure_ascii=False)

# nodes
nodes = pd.concat([pd.read_csv(f"{r}/processed/stage1/nodes.csv", keep_default_na=False)
                   for _, r in SHARDS], ignore_index=True)
n_nodes_raw = len(nodes)
nodes = nodes.drop_duplicates(subset=["name"], keep="first")
nodes.to_csv(f"{OUT}/processed/stage1/nodes.csv", index=False)
node_names = set(nodes["name"]); n_nodes = len(node_names); del nodes

# relations
rels = pd.concat([pd.read_csv(f"{r}/processed/stage1/relations.csv", keep_default_na=False)
                  for _, r in SHARDS], ignore_index=True)
n_rels_raw = len(rels)
rels = rels.drop_duplicates(subset=["name"], keep="first")
rels.to_csv(f"{OUT}/processed/stage1/relations.csv", index=False)
n_rels = len(rels); del rels

# edges
edges = pd.concat([pd.read_csv(f"{r}/processed/stage1/edges.csv", keep_default_na=False)
                   for _, r in SHARDS], ignore_index=True)
n_edges_raw = len(edges)
edges = edges.drop_duplicates(subset=["source", "relation", "target"], keep="first")
n_edges = len(edges)
missing = (~edges["source"].isin(node_names)).sum() + (~edges["target"].isin(node_names)).sum()
edges.to_csv(f"{OUT}/processed/stage1/edges.csv", index=False)

print("=== union-0-5 method-3 merge ===")
print(f"documents : {len(docs):>8}  ({dup_docs} dup titles collapsed across shards)")
print(f"nodes     : {n_nodes_raw:>8} -> {n_nodes:>8}  ({n_nodes_raw-n_nodes} cross-shard dups removed)")
print(f"relations : {n_rels_raw:>8} -> {n_rels:>8}")
print(f"edges     : {n_edges_raw:>8} -> {n_edges:>8}  ({n_edges_raw-n_edges} dups removed)")
print(f"edge endpoints missing from nodes: {missing} (0 expected)")
