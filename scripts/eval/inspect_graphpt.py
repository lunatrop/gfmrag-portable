import torch, json
FP = "71345f28ce99ab5be49b591c8c642cc6"
g = torch.load(f"corpus-shards/union-0-5/processed/stage2/{FP}/graph.pt",
               weights_only=False, map_location="cpu")
print("type:", type(g).__name__)
print("repr:", g)
try:
    for k in g.keys():
        v = g[k]
        print(f"  {k}: {type(v).__name__} {getattr(v, 'shape', '')}")
except Exception as e:
    print("keys() failed:", e)
print("feat_dim:", getattr(g, "feat_dim", None))
n2i = json.load(open(f"corpus-shards/union-0-5/processed/stage2/{FP}/node2id.json"))
print("node2id entries:", len(n2i))
