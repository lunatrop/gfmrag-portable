"""Quantitative retrieval/QA eval against the live gfmrag-qa service.

Generates a test set from the register CSV (gold answers are free — the corpus
is derived from structured data), queries /answer for each question, and scores:

  - retrieval hit@k : gold document appears in the retrieved docs
  - answer accuracy : gold answer string appears (normalised) in the answer

Usage (label tags the output file, e.g. the checkpoint under test):
    python scripts/qa_eval.py --label 34M \
        --documents corpus-shards/shard-0/raw/documents.json

Requires: gcloud auth (caller must hold run.invoker), terraform state for the
qa_url output (or pass --url).
"""

import argparse
import csv
import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path

IDX_RE = re.compile(r"Modern slavery statement (\S+):")


def norm(s: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split())


def entity_names(reporting_entities: str) -> list[str]:
    parts = re.split(r"\)\s*,\s*", reporting_entities or "")
    out = []
    for p in parts:
        p = re.sub(r"\(\s*[\d\s]+$", "", p.strip().rstrip(",")).strip()
        p = re.sub(r"\([\d\s]+\)$", "", p).strip()
        if p:
            out.append(p)
    return out


def build_testset(documents: Path, register: Path) -> list[dict]:
    reg = {}
    with open(register, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            reg[row["IDX"].strip()] = row

    tests = []
    for title in json.load(open(documents)):
        m = IDX_RE.match(title)
        if not m or m.group(1) not in reg:
            continue
        row = reg[m.group(1)]
        names = entity_names(row["ReportingEntities"])
        first = names[0]
        if row.get("IndustrySectors"):
            tests.append({
                "q": f"What industry sectors does {first} operate in?",
                "gold_answer": row["IndustrySectors"].split(",")[0].strip(),
                "gold_doc": title,
            })
        if row.get("AnnualRevenue"):
            tests.append({
                "q": f"What is the annual revenue band of {first}?",
                "gold_answer": row["AnnualRevenue"],
                "gold_doc": title,
            })
        if row.get("PeriodStart"):
            tests.append({
                "q": f"Which reporting period does the modern slavery statement of {first} cover?",
                "gold_answer": row["PeriodStart"],
                "gold_doc": title,
            })
        if len(names) > 1:  # multi-hop-ish: joint co-filers
            tests.append({
                "q": f"Which entities filed a joint modern slavery statement with {names[-1]}?",
                "gold_answer": first,
                "gold_doc": title,
            })
    return tests


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--label", required=True)
    ap.add_argument("--documents", type=Path, required=True)
    ap.add_argument("--register", type=Path, default="corpus/all-statements_2026-04-18.csv")
    ap.add_argument("--url", default=None)
    ap.add_argument("--top-k", type=int, default=5)
    args = ap.parse_args()

    url = args.url or subprocess.check_output(
        ["terraform", "-chdir=deploy/cloudrun", "output", "-raw", "qa_url"], text=True
    ).strip()
    token = subprocess.check_output(
        ["gcloud", "auth", "print-identity-token"], text=True
    ).strip()

    tests = build_testset(args.documents, args.register)
    print(f"{len(tests)} questions -> {url}  [{args.label}]")

    hits = answers_ok = 0
    results = []
    for i, t in enumerate(tests):
        body = json.dumps({"query": t["q"], "top_k": args.top_k}).encode()
        req = urllib.request.Request(
            f"{url}/answer", data=body,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"})
        start = time.time()
        resp = json.load(urllib.request.urlopen(req, timeout=900))
        elapsed = time.time() - start

        retrieved_ids = [d.get("id", "") for d in resp.get("retrieved", {}).get("document", [])]
        hit = t["gold_doc"] in retrieved_ids
        ans_ok = norm(t["gold_answer"]) in norm(str(resp.get("answer", "")))
        hits += hit
        answers_ok += ans_ok
        results.append({**t, "hit": hit, "answer_ok": ans_ok,
                        "answer": resp.get("answer"), "secs": round(elapsed, 1)})
        print(f"  [{i+1:2d}/{len(tests)}] hit={'Y' if hit else 'n'} "
              f"ans={'Y' if ans_ok else 'n'} {elapsed:5.1f}s  {t['q'][:70]}")

    out = Path(f"tmp/qa-eval-{args.label}.json")
    out.write_text(json.dumps({
        "label": args.label, "n": len(tests),
        "retrieval_hit_at_k": round(hits / len(tests), 3),
        "answer_accuracy": round(answers_ok / len(tests), 3),
        "results": results,
    }, indent=1))
    print(f"\n[{args.label}] retrieval hit@{args.top_k}: {hits}/{len(tests)} "
          f"({100*hits/len(tests):.0f}%)  answer accuracy: {answers_ok}/{len(tests)} "
          f"({100*answers_ok/len(tests):.0f}%)  -> {out}")


if __name__ == "__main__":
    main()
