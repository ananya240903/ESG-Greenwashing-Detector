# ESG Greenwashing Detector

Reads Indian BRSR (Business Responsibility and Sustainability Report) PDFs and checks whether a
company's environmental claims are backed by evidence in the same report.

> **Status:** Phase 1 (foundation) of the revamp is in place. The pipeline parses real BRSR PDFs
> into section-aware chunks, embeds them, and scores them with the original FinBERT heuristic,
> which is kept as the baseline. Claim extraction, evidence retrieval and verdicts come next.

## Architecture

```
            PDF + company + year
                    │
             ┌──────▼───────┐   report.uploaded   ┌───────────────┐   report.parsed   ┌─────────────────┐
             │ ingestor-api │ ──────────────────▶ │ parser-worker │ ────────────────▶ │ analyzer-worker │
             │ Spring Boot  │      (Kafka)        │ PyMuPDF, bge  │      (Kafka)      │ FinBERT baseline│
             └──────┬───────┘                     └───────┬───────┘                   └────────┬────────┘
                    └────────────── Postgres + pgvector (reports, chunks, scores) ─────────────┘
```

- **ingestor-api** (Java 17, Spring Boot 3): accepts the PDF upload, stores the file, records a
  `reports` row and publishes `{"reportId": N}`. Kafka carries IDs, never text.
- **parser-worker** (Python): extracts text and tables with PyMuPDF, splits them by BRSR section
  (A, B, C) and principle (1–9), then embeds each chunk with `BAAI/bge-small-en-v1.5`.
- **analyzer-worker** (Python): scores each text chunk with the FinBERT heuristic
  (`yiyanghkust/finbert-esg` + `ProsusAI/finbert`).
- **Postgres + pgvector**: one schema for everything ([db/init/001_schema.sql](db/init/001_schema.sql)),
  including the tables for the claims, evidence and verdicts that later phases will fill.

Parsing and inference run as separate workers, so a slow model never holds up parsing, and each
worker type can be scaled on its own (each topic has three partitions).

## Run it

Needs Docker. The first start downloads about 1 GB of models into a cached volume.

```bash
docker compose up --build
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
# Python: parser tests, and parse PDFs with no database or Kafka
cd nlp-analyzer
python -m venv ../.venv && ../.venv/Scripts/pip install -r requirements.txt   # bin/ on macOS/Linux
../.venv/Scripts/python -m pytest
../.venv/Scripts/python scripts/parse_pdf.py ../data/brsr/*.pdf

# Java: API tests run on in-memory H2, so no Postgres or Kafka needed
cd ingestor-api && mvn test
```

## Parsing results on real reports

Five FY2023-24 BRSRs, from five sectors:

| Report | Pages | Chunks (text / table) | Section A / B / C starts on page | Principles found |
|---|---|---|---|---|
| Axis Bank | 41 | 119 / 79 | 1 / 6 / 11 | 1–9 |
| HUL | 75 | 163 / 78 | 10 / 20 / 26 | 1–9 |
| NTPC | 40 | 101 / 76 | 2 / 9 / 12 | 1–9 |
| Tata Steel | 80 | 199 / 117 | 2 / 22 / 27 | 1–9 |
| Wipro | 47 | 104 / 73 | 2 / 9 / 12 | 1–9 |

## Roadmap

1. **Foundation**: Postgres instead of H2 and `.jsonl`, one docker-compose, PDF parsing *(done)*
2. **Claims**: fine-tuned claim and specificity classifiers, evaluation harness, baseline numbers
3. **Verification**: evidence retrieval (BM25 + pgvector + reranker), verdict model, hand-labelled gold set
4. **Surface**: dashboard, and a worked example with a metrics table
