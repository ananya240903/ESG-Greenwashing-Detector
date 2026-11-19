# nlp-analyzer

The Python side of the pipeline: two Kafka workers that share one package, `esg`.

| Worker | Consumes | Does | Produces |
|---|---|---|---|
| `python -m esg.workers.parser_worker` | `report.uploaded` | Parses the PDF, splits it by BRSR section and principle, embeds the chunks | `report.parsed` |
| `python -m esg.workers.analyzer_worker` | `report.parsed` | Scores text chunks with the FinBERT baseline | — |

Offsets are committed only after a report is handled, and both workers replace a report's rows
rather than appending to them, so a crash or a re-sent message never duplicates data.

## Layout

```
esg/
  parsing/
    pdf.py        PyMuPDF: text blocks and tables in reading order; drops running headers/footers
    sections.py   BRSR heading detection (Section A/B/C, Principle 1-9, Essential/Leadership Indicators)
    chunker.py    ~200-word prose chunks and row-sliced tables that never cross a principle boundary
  embedding.py    BAAI/bge-small-en-v1.5, 384-d normalised vectors
  baseline.py     the original FinBERT heuristic, unchanged, kept as the baseline to beat
  db.py           Postgres (psycopg 3 + pgvector)
  kafka_io.py     consumer loop and producer (confluent-kafka)
  workers/        the two entry points
scripts/parse_pdf.py   parse PDFs locally, with no database or Kafka
report_generator.py    bar chart of baseline risk per report, from Postgres
tests/                 parser unit tests (pytest)
```

## Baseline

Kept from the first version of the project, so later models have a number to beat:
`risk = sentiment confidence × (1 − ESG confidence) × 100`. A chunk is flagged when it is both
vague (ESG label `None` or confidence < 0.7) and hyped (positive with confidence > 0.5).

## Settings

`DATABASE_URL`, `KAFKA_BOOTSTRAP`, `REPORTS_DIR`, `EMBED_MODEL`, `ESG_MODEL`, `TONE_MODEL`; see
[esg/config.py](esg/config.py) for the defaults.
