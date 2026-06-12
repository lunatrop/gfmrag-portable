import pandas as pd, collections, json

base = "corpus-shards/shard-4/processed/stage1"
nodes = pd.read_csv(f"{base}/nodes.csv", keep_default_na=False)
rels = pd.read_csv(f"{base}/relations.csv", keep_default_na=False)
edges = pd.read_csv(f"{base}/edges.csv", keep_default_na=False)

print("=== node type distribution ===")
print(nodes["type"].value_counts().to_string())

print("\n=== all relation names (103) ===")
print(", ".join(sorted(rels["name"].tolist())))

print("\n=== top 25 relations by edge frequency ===")
for r, c in collections.Counter(edges["relation"]).most_common(25):
    print(f"  {c:>7}  {r}")

print("\n=== sample ENTITY-type node names (30) ===")
ents = nodes[nodes["type"] != "document"]["name"].tolist()
print("\n".join("  " + e for e in ents[:30]))

print("\n=== sample targets for key relations (what values exist) ===")
for rel in ["has abn", "has revenue", "operates in sector", "headquartered in",
            "has annual revenue", "operates in", "located in", "reporting period",
            "has reporting period", "annual revenue", "industry sector", "sector"]:
    sub = edges[edges["relation"] == rel]
    if len(sub):
        vals = sub["target"].value_counts().head(8)
        print(f"\n  [{rel}] ({len(sub)} edges) top targets:")
        for v, c in vals.items():
            print(f"      {c:>5}  {v[:70]}")
