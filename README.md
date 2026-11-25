# ESG Greenwashing Detector

Reads Indian BRSR (Business Responsibility and Sustainability Report) PDFs and checks whether a
company's environmental claims are backed by evidence in the same report.

> **Status:** Phases 1–3 are done. The pipeline parses real BRSR PDFs into section-aware chunks,
> extracts environmental claims with fine-tuned classifiers, retrieves evidence for each claim
> from the same report, and labels it substantiated, vague or unsupported with a cited reason.
> Every stage is measured, against public datasets and a hand-labelled BRSR gold set, alongside
> the original FinBERT heuristic as the baseline. A dashboard shows each report's claims with
> their evidence and verdict.

## Architecture

```
            PDF + company + year
                    │
             ┌──────▼───────┐   report.uploaded   ┌───────────────┐   report.parsed   ┌─────────────────┐
             │ ingestor-api │ ──────────────────▶ │ parser-worker │ ────────────────▶ │ analyzer-worker │
             │ Spring Boot  │      (Kafka)        │ PyMuPDF, bge  │      (Kafka)      │ claims, verdicts│
             └──────┬───────┘                     └───────┬───────┘                   └────────┬────────┘
                    └────────────── Postgres + pgvector (chunks, claims, verdicts) ────────────┘
```

- **ingestor-api** (Java 17, Spring Boot 3): accepts the PDF upload, stores the file, records a
  `reports` row and publishes `{"reportId": N}`. Kafka carries IDs, never text.
- **parser-worker** (Python): extracts text and tables with PyMuPDF, splits them by BRSR section
  (A, B, C) and principle (1–9), then embeds each chunk with `BAAI/bge-small-en-v1.5`.
- **analyzer-worker** (Python): finds environmental claim sentences and scores how specific each
  one is, with two fine-tuned ClimateBERT classifiers. For each claim it retrieves evidence from
  the same report (BM25 + pgvector, fused, then a cross-encoder reranker) and gives a verdict with
  an NLI model and a few explicit rules. It also scores each chunk with the original FinBERT
  heuristic (`yiyanghkust/finbert-esg` + `ProsusAI/finbert`) as the baseline.
- **Postgres + pgvector**: one schema for everything ([db/init/001_schema.sql](db/init/001_schema.sql)),
  plus the `report_risk` view ([db/init/002_report_risk.sql](db/init/002_report_risk.sql)).

Parsing and inference run as separate workers, so a slow model never holds up parsing, and each
worker type can be scaled on its own (each topic has three partitions).

## Run it

Needs Docker. The first start downloads about 1 GB of models into a cached volume.

```bash
docker compose up --build
```

Claim extraction needs the two fine-tuned classifiers, which are not in git. Train them once
(about 40 minutes on CPU; see [nlp-analyzer](nlp-analyzer/README.md#claim-extraction)):

```bash
docker compose run --rm tools python -m scripts.train_classifier --task claims
docker compose run --rm tools python -m scripts.train_classifier --task specificity
docker compose restart analyzer-worker
```

Upload a report (`fiscalYear` is the year the financial year ends, so FY2023-24 is `2024`):

```bash
curl -F file=@tatasteel_fy2023-24.pdf -F company="Tata Steel" -F fiscalYear=2024 \
     http://127.0.0.1:8080/api/reports
```

Then watch it move through `UPLOADED → PARSING → PARSED → ANALYZING → ANALYZED`:

```bash
curl http://127.0.0.1:8080/api/reports/1
```

| Endpoint | Purpose |
|---|---|
| `POST /api/reports` | Upload a PDF (multipart: `file`, `company`, `fiscalYear`). Returns 202, or 200 if the same file was uploaded before |
| `GET /api/reports?company=` | List reports, optionally filtered by company name |
| `GET /api/reports/{id}` | One report and its status |
| `POST /api/reports/{id}/reprocess` | Send a report through the pipeline again |
| `GET /api/reports/risk` | Every analysed report with its verdict counts and risk score, riskiest first |
| `GET /api/reports/{id}/claims?verdict=` | A report's claims in reading order, each with its verdict, cited reason and top 3 evidence passages; `verdict` filters to `substantiated`, `vague` or `unsupported` |

The **dashboard** is at <http://127.0.0.1:8501>. The Overview page ranks the reports by risk score;
select one to open its Report page, which lists every claim with its verdict, the reason, and the
passages retrieved as evidence, with filters by verdict and a text search. It reads only from the
API ([dashboard/](dashboard/)).

Other ports: Postgres on `5432` (user/password/db `esg`), Kafdrop (Kafka UI) on `9000`.

## Develop without Docker

```bash
# Python: unit tests, and parse PDFs with no database or Kafka
cd nlp-analyzer
python -m venv ../.venv && ../.venv/Scripts/pip install -r requirements.txt   # bin/ on macOS/Linux
../.venv/Scripts/python -m pytest
../.venv/Scripts/python scripts/parse_pdf.py ../data/brsr/*.pdf

# Evaluation harness and regression gate (in Docker, where the models run)
docker compose run --rm tools python -m scripts.evaluate
docker compose run --rm tools python -m pytest -m eval

# Java: API tests run on in-memory H2, so no Postgres or Kafka needed
cd ingestor-api && ./mvnw test      # mvnw.cmd on Windows
```

> On Windows with WSL, use `127.0.0.1` rather than `localhost`: WSL can hold `[::1]:8080`.

## Parsing results on real reports

Five FY2023-24 BRSRs, from five sectors:

| Report | Pages | Chunks (text / table) | Section A / B / C starts on page | Principles found |
|---|---|---|---|---|
| Axis Bank | 41 | 119 / 79 | 1 / 6 / 11 | 1–9 |
| HUL | 75 | 163 / 78 | 10 / 20 / 26 | 1–9 |
| NTPC | 40 | 101 / 76 | 2 / 9 / 12 | 1–9 |
| Tata Steel | 80 | 199 / 117 | 2 / 22 / 27 | 1–9 |
| Wipro | 47 | 104 / 73 | 2 / 9 / 12 | 1–9 |

## Claim models against the baseline

Positive-class F1 on each public dataset's held-out test split, with 95% bootstrap intervals.
Full tables, including precision, recall and ROC AUC: [nlp-analyzer/eval/metrics.md](nlp-analyzer/eval/metrics.md).

| Task | FinBERT baseline | Fine-tuned ClimateBERT |
|---|---|---|
| Is this sentence an environmental claim? (265 sentences) | 0.621 (0.54–0.69) | **0.844** (0.78–0.90) |
| Is this climate passage specific rather than vague? (320 paragraphs) | 0.541 (0.48–0.59) | **0.735** (0.66–0.79) |

The baseline finds most claims, but more than half of what it flags is not one (precision
0.46). On specificity it almost never flags anything, so it calls nearly every passage
specific; its ROC AUC of 0.61 is close to chance, against 0.88 for the fine-tuned model.

These are scores on the public datasets, which come from mostly European and US reports. How
well the models do on Indian BRSR text is measured in Phase 3, against a hand-labelled gold set.

### Claims found in the five BRSRs

| Report | Claims | In Section B | Specificity ≥ 0.5 | Mean specificity |
|---|---|---|---|---|
| Axis Bank | 47 | 0 | 10 | 0.25 |
| HUL | 185 | 31 | 41 | 0.23 |
| NTPC | 30 | 0 | 6 | 0.23 |
| Tata Steel | 144 | 11 | 23 | 0.19 |
| Wipro | 28 | 0 | 3 | 0.16 |

At the top of the specificity scale: *"we have achieved sustainable sourcing for 94% of our total
paper and board, 81% of our total tomatoes and 79% of our total tea"* (HUL, 1.00). At the bottom:
*"We have been taking steps to address the problem of plastics as well."* (0.01).

Do not read the "≥ 0.5" column as a count of specific claims yet. The specificity model was
trained on paragraphs, and single sentences score lower: *"source 100% renewable energy"*
scores 0.46. The worker stores the raw scores, and the cut-off between specific and vague is
calibrated in Phase 3 against the gold set.

## Verification on the BRSR gold set

200 claim sentences from the five reports were hand-labelled: is it really an environmental claim,
is it substantiated, vague or unsupported, and which passages back it. Test numbers are on
held-out claims; thresholds were tuned on a separate dev split. Full tables, with confidence
intervals and the confusion matrix: [nlp-analyzer/eval/gold_metrics.md](nlp-analyzer/eval/gold_metrics.md).

| Stage | Result |
|---|---|
| Claim extraction: share of extracted sentences that are real claims | 0.73 (95% CI 0.66–0.78) |
| Retrieval: a supporting passage in the top 3 (81 substantiated claims) | **0.91** with the reranker; 0.84 BM25, 0.83 vector |
| Verdicts: macro F1 over the three labels (87 test claims) | 0.39–0.48 by rule variant; FinBERT baseline 0.26, majority class 0.23 |

What this shows:

- **Retrieval works.** Fusing BM25 with vector search and reranking finds the backing passage
  for 9 in 10 substantiated claims; the reranker lifts hit@3 from 0.86 (fused) to 0.91.
- **Verdicts are the weak stage.** Every variant beats the baseline, but none is reliable. The
  NLI model barely separates substantiated from unsupported claims (ROC AUC 0.62), largely because
  much of the evidence is tables of figures, which NLI models are not trained on. The rule
  selected on dev (evidence first, with NLI or reranker relevance counting as support) is
  generous with "substantiated" and rarely calls a claim vague.
- **The labels have limits.** One person labelled everything, at a median of 16 seconds per
  claim. A second pass over the test claims agreed with the first on 84% (Cohen's kappa 0.73),
  so the labels are consistent, but they were not checked carefully against every passage.

### Risk scores

The share of each report's claims that are vague or unsupported, weighted so that headline
claims in Section B count 1.5x. Given the verdict stage's bias towards "substantiated", treat
these as lower bounds for comparing reports, not as findings about the companies.

| Report | Claims | Substantiated | Vague | Unsupported | Risk score |
|---|---|---|---|---|---|
| HUL | 185 | 146 | 19 | 20 | 20.0 |
| Axis Bank | 42 | 30 | 1 | 11 | 28.6 |
| Tata Steel | 143 | 100 | 20 | 23 | 29.3 |
| Wipro | 28 | 15 | 6 | 7 | 46.4 |
| NTPC | 25 | 13 | 5 | 7 | 48.0 |

## Worked example

One claim from HUL's FY2023-24 BRSR, end to end. On page 32, under Principle 2, the report has a
headline figure:

> 94% Sustainable sourcing of paper and board

1. **Parsing.** The parser puts it in a Section C, Principle 2 text chunk on page 32.
2. **Claim extraction.** The claim classifier scores it 0.91, so it is kept as an environmental claim.
   The specificity classifier gives 0.45: it has a figure, but it is a heading fragment, not a sentence.
3. **Retrieval.** BM25 and vector search over the report's other chunks are fused, and the rest of
   the claim's own chunk is added as a candidate. The reranker puts that chunk first (relevance 6.9).
   It says *"we have achieved sustainable sourcing for 94% of our total paper and board, 81% of our
   total tomatoes and 79% of our total tea procured during the calendar year 2023."* Second (4.1) is
   the CEO's letter on page 3; third (3.5) is the director's statement on page 23.
4. **Verdict.** NLI scores the top passage as entailing the claim (0.91), so the claim is
   **substantiated**, with the reason *"Backed by text, Principle 2, p. 32 (entailment 0.91)."*
   The hand label agrees.

The same claim from the API (`GET /api/reports/2/claims`, trimmed):

```json
{
  "id": 1456,
  "sentence": "94% Sustainable sourcing of paper and board",
  "location": { "kind": "text", "section": "C", "principle": 2, "page": 32 },
  "claimScore": 0.914,
  "specificityScore": 0.451,
  "verdict": {
    "label": "substantiated",
    "confidence": 0.907,
    "reason": "Backed by text, Principle 2, p. 32 (entailment 0.91).",
    "citedChunkIds": [4901]
  },
  "evidence": [
    { "rank": 1, "location": { "kind": "text", "section": "C", "principle": 2, "page": 32 },
      "rerankScore": 6.94, "cited": true, "text": "48.1%* of key crops were sourced sustainably. ..." },
    { "rank": 2, "location": { "kind": "text", "section": null, "principle": null, "page": 3 },
      "rerankScore": 4.11, "cited": false, "text": "Chief Executive Officer and Managing Director ..." },
    { "rank": 3, "location": { "kind": "text", "section": "B", "principle": null, "page": 23 },
      "rerankScore": 3.49, "cited": false, "text": "We believe that corporates will need to play ..." }
  ]
}
```

**And one it gets wrong.** Wipro: *"We estimate that close to more than 50% of suppliers by value of
business would be assessed for environmental impact."* The model calls it substantiated, citing a
passage on page 33 (reranker relevance 2.8). That passage is the same sentence printed again in the
report, so the claim is backing itself. The hand label is unsupported. 22 of the 304 substantiated
verdicts (7%) cite a passage that contains the claim word for word. Dropping such passages from
retrieval is the first fix in the list below.

## Roadmap

1. **Foundation**: Postgres instead of H2 and `.jsonl`, one docker-compose, PDF parsing *(done)*
2. **Claims**: fine-tuned claim and specificity classifiers, evaluation harness, baseline numbers *(done)*
3. **Verification**: evidence retrieval (BM25 + pgvector + reranker), verdict model, hand-labelled gold set *(done)*
4. **Surface**: dashboard, API for claims and risk, worked example *(done)*

Next steps for the verdict stage, in order of expected gain:

1. Drop retrieved passages that contain the claim word for word, so a repeated sentence cannot
   back itself (7% of substantiated verdicts today).
2. A careful second labeller, to measure agreement properly.
3. A numeric check that matches figures in a claim against the report's tables (the "words versus
   numbers" check in the plan). NLI handles tables poorly.
4. An LLM judge, as a comparison.
