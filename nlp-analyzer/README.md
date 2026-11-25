# nlp-analyzer

The Python side of the pipeline: two Kafka workers that share one package, `esg`, plus the
training, labelling and evaluation tools for the claim and verdict models.

| Worker | Consumes | Does | Produces |
|---|---|---|---|
| `python -m esg.workers.parser_worker` | `report.uploaded` | Parses the PDF, splits it by BRSR section and principle, embeds the chunks | `report.parsed` |
| `python -m esg.workers.analyzer_worker` | `report.parsed` | Scores text chunks with the FinBERT baseline; extracts environmental claims; retrieves evidence for each and gives a verdict | — |

Offsets are committed only after a report is handled, and both workers replace a report's rows
rather than appending to them, so a crash or a re-sent message never duplicates data. If
Postgres restarts mid-job, the worker reconnects and re-runs the job (`db.Session`).

## Layout

```
esg/
  parsing/
    pdf.py        PyMuPDF: text blocks and tables in reading order; drops running headers/footers
    sections.py   BRSR heading detection (Section A/B/C, Principle 1-9, Essential/Leadership Indicators)
    chunker.py    ~200-word prose chunks and row-sliced tables that never cross a principle boundary
  claims/
    sentences.py  chunk text -> candidate sentences with offsets; drops BRSR questions, template text, fragments
    classifier.py loads a fine-tuned classifier and returns P(label = 1)
    extract.py    sentences -> claim classifier -> specificity classifier -> prominence
  retrieval/
    bm25.py       Okapi BM25 over one report's chunks (keeps figures and units as tokens)
    search.py     BM25 + vector search, reciprocal rank fusion, cross-encoder reranking
  verdict/
    nli.py        NLI entailment/contradiction over ~110-word windows of each passage
    rules.py      scores -> substantiated / vague / unsupported, with a cited reason
    verify.py     claims -> evidence -> verdicts for one report (worker and evaluation share it)
  eval/
    datasets.py   the public labelled datasets, pinned files and fixed splits
    gold.py       the hand-labelled BRSR gold set: items, labels, dev/test split
    systems.py    every system under comparison (FinBERT baseline readings, fine-tuned models)
    metrics.py    precision/recall/F1, ROC AUC, bootstrap confidence intervals
  embedding.py    BAAI/bge-small-en-v1.5, 384-d normalised vectors
  baseline.py     the original FinBERT heuristic, unchanged, kept as the baseline to beat
  db.py           Postgres (psycopg 3 + pgvector), with reconnect-and-retry
  kafka_io.py     consumer loop and producer (confluent-kafka)
  workers/        the two entry points
scripts/
  train_classifier.py  fine-tune the claim or specificity classifier
  evaluate.py          the evaluation harness; writes eval/metrics.{json,md}
  export_gold_items.py sample claims and pool their evidence for labelling
  evaluate_gold.py     score claims, retrieval and verdicts on the gold set; writes eval/gold_metrics.{json,md}
  parse_pdf.py         parse PDFs locally, with no database or Kafka
eval/                  committed results (metrics, gold-set metrics, predictions) and gold/ labels
label_app.py           Streamlit app for labelling the gold set
models/                trained classifiers (not in git; rebuild with train_classifier.py)
report_generator.py    bar chart of baseline risk per report, from Postgres
tests/                 unit tests; `pytest -m eval` adds the evaluation gate
```

## Claim extraction

1. **Sentences.** Each text chunk is split into sentences, keeping character offsets. BRSR
   question lines (`EI-6. Please provide…`), the nine principle statements printed in every
   report (`Businesses should…`), headings, numeric table rows and fragments are dropped.
2. **Claim classifier.** A sentence is kept as an environmental claim when P(claim) ≥ 0.5
   (`CLAIM_THRESHOLD`).
3. **Specificity classifier.** Each claim gets P(specific): figures, targets and concrete
   actions score high; "we are committed to a greener planet" scores low.
4. **Prominence.** Claims in Section B (the director's statement and headline commitments)
   weigh 1.5, others 1.0. The Phase 3 risk score weights claims by this.

Both classifiers fine-tune `climatebert/distilroberta-base-climate-f` (DistilRoBERTa
further pre-trained on climate text) on the public ClimateBERT datasets:

| Task | Dataset | Train / validation / test | Positive |
|---|---|---|---|
| Claims | `climatebert/environmental_claims` (sentences) | 2,117 / 265 / 265 | 25% |
| Specificity | `climatebert/climate_specificity` (paragraphs) | 850 / 150 / 320 | 40% |

The specificity dataset publishes no validation split, so 15% of its train split is held out
(stratified, seed 42) to pick the best epoch. Both datasets are CC BY-NC-SA 4.0 (research use).

Train (about 15 and 25 minutes on a 6-core CPU):

```bash
docker compose run --rm tools python -m scripts.train_classifier --task claims
docker compose run --rm tools python -m scripts.train_classifier --task specificity
docker compose restart analyzer-worker   # picks up the new models
```

Without trained models the analyzer still runs the baseline and logs a warning.

## Evaluation harness

```bash
docker compose run --rm tools python -m scripts.evaluate    # rewrites eval/metrics.{json,md}
docker compose run --rm tools python -m pytest -m eval      # fails if a model regresses
```

`scripts/evaluate.py` scores every system on each task's test split and records which models
and data produced the numbers. The results are committed, so a change in the numbers shows up
in review. `pytest -m eval` re-runs the evaluation and fails if a fine-tuned model drops below
its F1 floor or stops beating the best baseline by 0.15 F1. Phase 3 adds the BRSR gold set and
the verdict task to the same harness. Current results: [eval/metrics.md](eval/metrics.md).

## Evidence retrieval

For each claim, candidate evidence comes from the claim's own report:

1. **BM25** and **vector search** (bge-small embeddings, with bge's query instruction) each
   rank every chunk, text and tables alike. The claim's own chunk is left out, since it
   contains the claim word for word.
2. **Reciprocal rank fusion** merges the two rankings; the top 20 go on.
3. The rest of the claim's own chunk, with the claim cut out, joins them as one more candidate.
4. A **cross-encoder** (`cross-encoder/ms-marco-MiniLM-L-6-v2`) reranks the candidates; the
   top 3 are stored in `evidence`.

## Verdicts

An NLI model (`cross-encoder/nli-roberta-base`) scores each evidence passage against the
claim. Passages are cut into overlapping ~110-word windows, because NLI models are trained
on short premises, and a passage scores the highest entailment and contradiction over its
windows. [esg/verdict/rules.py](esg/verdict/rules.py) turns the scores into a verdict with a
cited reason, checking in this order:

1. **Unsupported:** a passage contradicts the claim (P ≥ 0.7) more strongly than any passage
   supports it. The reason cites the contradicting passage.
2. **Substantiated:** a passage supports it, either NLI entailment ≥ 0.2 or reranker relevance
   ≥ 0. The reason cites that passage.
3. **Vague:** nothing supports it and specificity < 0.05.
4. **Unsupported:** nothing supports it.

These settings were chosen on the gold set's dev split (`VERDICT_ORDER`, `VAGUE_BELOW`,
`ENTAIL_AT`, `CONTRADICT_AT`, `RERANK_AT`). The report risk score is the Postgres view
`report_risk`: the prominence-weighted share of a report's claims that are vague or
unsupported ([db/init/002_report_risk.sql](../db/init/002_report_risk.sql)).

Model choices were driven by CPU time. DeBERTa-v3 NLI was 12x slower than RoBERTa here
(2.6 s per window against 0.22 s), and `bge-reranker-base` about 7x slower than MiniLM.

## Gold set

200 claim sentences from the five FY2023-24 BRSRs, hand-labelled. For each one the labeller
answers whether it is really an environmental claim, gives a verdict, and ticks the passages
that back it.

- **Sampling:** every claim from the three smaller reports, and an even spread over the
  specificity range from HUL and Tata Steel.
- **Passages shown:** the union of the top 3 from BM25, vector search, hybrid and hybrid +
  reranker, shuffled. This pooling is what lets retrieval be scored without the labeller
  favouring any one system.
- **Splits:** each item goes to dev (40%, used for tuning) or test (60%, used for reporting)
  by a hash of its key.

```bash
docker compose run --rm tools python -m scripts.export_gold_items   # eval/gold/items.jsonl
pip install -r requirements-label.txt
streamlit run label_app.py                     # writes eval/gold/labels.jsonl
streamlit run label_app.py -- --second-pass    # re-label the test split -> labels_pass2.jsonl
docker compose run --rm tools python -m scripts.evaluate_gold       # eval/gold_metrics.md
```

Results and their limits: [eval/gold_metrics.md](eval/gold_metrics.md).

## Baseline

Kept from the first version of the project, so later models have a number to beat:
`risk = sentiment confidence × (1 − ESG confidence) × 100`. A chunk is flagged when it is both
vague (ESG label `None` or confidence < 0.7) and hyped (positive with confidence > 0.5).

It was not built for claim detection or specificity, so the harness maps it onto them as
directly as its outputs allow: a claim is a passage whose top FinBERT-ESG label is
Environmental; a passage is not specific when the old tool flags it (and, as a second, more
generous reading, whenever the ESG model is unsure).

## Settings

`DATABASE_URL`, `KAFKA_BOOTSTRAP`, `REPORTS_DIR`, `EMBED_MODEL`, `ESG_MODEL`, `TONE_MODEL`,
`MODELS_DIR`, `CLAIM_MODEL_DIR`, `SPECIFICITY_MODEL_DIR`, `CLAIM_THRESHOLD`, `RERANK_MODEL`,
`NLI_MODEL`, `EVIDENCE_K`, `RETRIEVAL_DEPTH`, and the verdict thresholds above; see
[esg/config.py](esg/config.py) for the defaults.
