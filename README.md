# ESG Greenwashing Detector

Reads Indian BRSR (Business Responsibility and Sustainability Report) PDFs and checks whether a
company's environmental claims are backed by evidence in the same report.

> **Status:** Phases 1 (foundation) and 2 (claims) are done. The pipeline parses real BRSR PDFs
> into section-aware chunks, embeds them, and extracts environmental claims with fine-tuned
> classifiers that score how specific each claim is. The original FinBERT heuristic is kept as
> the baseline, and an evaluation harness compares them. Evidence retrieval and verdicts come next.

## Architecture

```
            PDF + company + year
                    │
             ┌──────▼───────┐   report.uploaded   ┌───────────────┐   report.parsed   ┌─────────────────┐
             │ ingestor-api │ ──────────────────▶ │ parser-worker │ ────────────────▶ │ analyzer-worker │
             │ Spring Boot  │      (Kafka)        │ PyMuPDF, bge  │      (Kafka)      │ claims + spec.  │
             └──────┬───────┘                     └───────┬───────┘                   └────────┬────────┘
                    └────────────── Postgres + pgvector (reports, chunks, scores) ─────────────┘
```

- **ingestor-api** (Java 17, Spring Boot 3): accepts the PDF upload, stores the file, records a
  `reports` row and publishes `{"reportId": N}`. Kafka carries IDs, never text.
- **parser-worker** (Python): extracts text and tables with PyMuPDF, splits them by BRSR section
  (A, B, C) and principle (1–9), then embeds each chunk with `BAAI/bge-small-en-v1.5`.
- **analyzer-worker** (Python): finds environmental claim sentences and scores how specific each
  one is, with two fine-tuned ClimateBERT classifiers; also scores each chunk with the original
  FinBERT heuristic (`yiyanghkust/finbert-esg` + `ProsusAI/finbert`) as the baseline.
- **Postgres + pgvector**: one schema for everything ([db/init/001_schema.sql](db/init/001_schema.sql)),
  including the tables for the claims, evidence and verdicts that later phases will fill.

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

## Roadmap

1. **Foundation**: Postgres instead of H2 and `.jsonl`, one docker-compose, PDF parsing *(done)*
2. **Claims**: fine-tuned claim and specificity classifiers, evaluation harness, baseline numbers *(done)*
3. **Verification**: evidence retrieval (BM25 + pgvector + reranker), verdict model, hand-labelled gold set
4. **Surface**: dashboard, and a worked example with a metrics table
