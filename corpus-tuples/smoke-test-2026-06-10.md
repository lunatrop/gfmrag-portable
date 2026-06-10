# Ollama smoke test — 2026-06-10

Passage: register-style text built from the first joint-statement row of
`corpus/all-statements_2026-04-18.csv` (Endeavour Group / Woolworths, 2019-20).

| Model | Time | Entities | Triples | Verdict |
|---|---|---|---|---|
| gemma2:2b (local default) | 173.6s | 10 | **0** | ❌ answered the triple prompt in NER format |
| qwen2.5:3b | 194.9s | 9 | 10 | ✅ clean, domain-correct |

## qwen2.5:3b triples

```
(ENDEAVOUR GROUP LIMITED) --[filed a joint modern slavery statement with]--> (WOOLWORTHS GROUP LIMITED)
(ENDEAVOUR GROUP LIMITED) --[headquartered in]--> (Australia)
(ENDEAVOUR GROUP LIMITED) --[operates in the industry sector of]--> (agriculture and fishing)
(ENDEAVOUR GROUP LIMITED) --[has annual revenue over]--> (1 billion dollars)
(WOOLWORTHS GROUP LIMITED) --[filed a joint modern slavery statement with]--> (ENDEAVOUR GROUP LIMITED)
(WOOLWORTHS GROUP LIMITED) --[headquartered in]--> (Australia)
(WOOLWORTHS GROUP LIMITED) --[operates in the industry sector of]--> (agriculture and fishing)
(WOOLWORTHS GROUP LIMITED) --[has annual revenue over]--> (1 billion dollars)
(ENDEAVOUR GROUP LIMITED) --[filed a joint modern slavery statement for the period]--> (2019-07-01 to 2020-06-30)
(WOOLWORTHHS GROUP LIMITED) --[filed a joint modern slavery statement for the period]--> (2019-07-01 to 2020-06-30)
```

## Findings

1. **gemma2:2b fails on register-style text** despite passing the biography
   benchmark — for this corpus the local model should be **qwen2.5:3b**.
2. Note the typo'd subject in the last triple (`WOOLWORTHHS`) — a concrete
   example of why the fact-verification gate (exact-match entity names/ABNs
   against the register) is required before any lead-gen output.
3. NER quality is high across both models (companies, ABNs, dates, sectors).
