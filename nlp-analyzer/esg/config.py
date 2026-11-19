"""Settings read from the environment, with defaults for running outside Docker."""

import os
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://esg:esg@localhost:5432/esg")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
REPORTS_DIR = Path(os.getenv("REPORTS_DIR", "../data/reports"))

TOPIC_REPORT_UPLOADED = os.getenv("TOPIC_REPORT_UPLOADED", "report.uploaded")
TOPIC_REPORT_PARSED = os.getenv("TOPIC_REPORT_PARSED", "report.parsed")

EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBED_DIM = 384  # must match chunks.embedding in db/init/001_schema.sql
EMBED_BATCH = int(os.getenv("EMBED_BATCH", "32"))

ESG_MODEL = os.getenv("ESG_MODEL", "yiyanghkust/finbert-esg")
TONE_MODEL = os.getenv("TONE_MODEL", "ProsusAI/finbert")
