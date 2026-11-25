# Gold-set results (BRSR)

Generated 2026-11-25 by `python -m scripts.evaluate_gold` at commit `84ce940`.
200 hand-labelled sentences from five FY2023-24 BRSRs; 145 are real environmental claims (58 dev / 87 test). Verdicts: substantiated 81, unsupported 36, vague 28.

## Label quality

All labels come from one person. The first pass covered all 200 sentences; the 87 test-split claims were then labelled again with a stricter guide (a passage backs a claim only if it states the same specific fact) and the first answers hidden. Both passes were fast, at a median of 16 seconds per claim, so the labels are consistent but were not checked carefully against every passage. Test numbers below use the second pass; thresholds are tuned on the first-pass dev labels.

Agreement between the two passes: **84%** same answer, Cohen's kappa **0.73** (consistency, not accuracy). Most common changes: substantiated -> unsupported (8), unsupported -> substantiated (4), substantiated -> vague (2).

## Claim extraction on BRSR

Precision **0.725** (95% CI 0.66-0.78): the share of sentences the claim classifier picked that are real environmental claims. By company: Axis Bank 0.79, Hindustan Unilever 0.72, NTPC 0.76, Tata Steel 0.65, Wipro 0.75.

## Evidence retrieval

Over the 81 substantiated claims: is a passage the labeller marked as supporting ranked first (hit@1) or in the top 3 (hit@3)?

| System | Hit@1 | Hit@3 | MRR@3 |
|---|---|---|---|
| `bm25` | 0.593 | 0.840 | 0.710 |
| `vector` | 0.679 | 0.827 | 0.753 |
| `hybrid` | 0.679 | 0.864 | 0.763 |
| `hybrid_rerank` | 0.679 | 0.914 | 0.792 |

Rankings are judged by pooling: the labeller saw the union of every system's top 3. Only `hybrid_rerank` can return the rest of the claim's own passage.

## Verdicts (test split, 87 claims)

| System | What it does | Accuracy | Macro F1 (95% CI) | F1 substantiated / vague / unsupported | Flag F1 |
|---|---|---|---|---|---|
| `majority` | Always the most common dev label | 0.517 | **0.227** (0.20-0.26) | 0.68 / 0.00 / 0.00 | 0.000 |
| `finbert-flag` | Old tool: chunk flagged = vague, else substantiated | 0.529 | **0.261** (0.21-0.34) | 0.69 / 0.10 / 0.00 | 0.047 |
| `specificity-only` | Specificity < 0.5 = vague, else substantiated (no evidence) | 0.345 | **0.261** (0.19-0.33) | 0.36 / 0.42 / 0.00 | 0.611 |
| `nli-default` | Vague check first, then NLI; untuned (vague < 0.5, entail ≥ 0.5, contradict ≥ 0.8) | 0.333 | **0.314** (0.22-0.41) | 0.16 / 0.42 / 0.36 | 0.672 |
| `nli-vague-first` | Vague check first, then NLI; tuned on dev (vague < 0.05, entail ≥ 0.2, contradict ≥ 0.8), dev F1 0.32 | 0.402 | **0.399** (0.29-0.50) | 0.29 / 0.46 / 0.45 | 0.672 |
| `nli-evidence-first` | NLI evidence check first, then vague; tuned on dev (vague < 0.05, entail ≥ 0.2, contradict ≥ 0.8), dev F1 0.39 | 0.471 | **0.467** (0.36-0.58) | 0.50 / 0.39 / 0.51 | 0.647 |
| `nli+rerank-evidence-first` | Evidence first; NLI or reranker relevance counts as support; tuned on dev (vague < 0.05, entail ≥ 0.2, contradict ≥ 0.7, rerank ≥ 0), dev F1 0.52 | 0.506 | **0.390** (0.29-0.48) | 0.65 / 0.07 / 0.45 | 0.486 |
| `nli+rerank+numbers` | As above, plus words vs numbers: the claim's figures found elsewhere in the report count as support, and figures found nowhere make it unsupported; tuned on dev (vague < 0.05, entail ≥ 0.3, contradict ≥ 0.8, rerank ≥ 2, numbers on), dev F1 0.54 **(selected on dev)** | 0.529 | **0.487** (0.37-0.60) | 0.64 / 0.29 / 0.54 | 0.602 |

Flag F1: vague or unsupported (a greenwashing flag) against substantiated. Each `nli-*` variant is tuned on the dev split only; the variant with the best dev score is selected, and every row is scored on the test split. Models: `cross-encoder/ms-marco-MiniLM-L-6-v2`, `cross-encoder/nli-roberta-base`.

How well each evidence signal separates substantiated from unsupported claims (117 claims, ROC AUC): NLI max entailment 0.595, reranker max relevance 0.594.

Confusion matrix for `nli+rerank+numbers` (rows = gold, columns = predicted):

| | substantiated | vague | unsupported |
|---|---|---|---|
| **substantiated** | 29 | 10 | 6 |
| **vague** | 12 | 6 | 2 |
| **unsupported** | 5 | 6 | 11 |

## Specificity on BRSR sentences

ROC AUC **0.680** for telling checkable claims (substantiated or unsupported) from vague ones. At the default 0.5 cut-off, F1 0.424; at the tuned 0.05, F1 0.629.
