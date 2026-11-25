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

# Phase 2: fine-tuned claim and specificity classifiers (scripts/train_classifier.py).
MODELS_DIR = Path(os.getenv("MODELS_DIR", "models"))
CLASSIFIER_BASE_MODEL = os.getenv("CLASSIFIER_BASE_MODEL", "climatebert/distilroberta-base-climate-f")
CLAIM_MODEL_DIR = Path(os.getenv("CLAIM_MODEL_DIR", str(MODELS_DIR / "claims")))
SPECIFICITY_MODEL_DIR = Path(os.getenv("SPECIFICITY_MODEL_DIR", str(MODELS_DIR / "specificity")))
CLAIM_THRESHOLD = float(os.getenv("CLAIM_THRESHOLD", "0.5"))

# Phase 3: evidence retrieval and verdicts.
RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
NLI_MODEL = os.getenv("NLI_MODEL", "cross-encoder/nli-roberta-base")
EVIDENCE_K = int(os.getenv("EVIDENCE_K", "3"))          # passages kept per claim
RETRIEVAL_DEPTH = int(os.getenv("RETRIEVAL_DEPTH", "20"))  # candidates sent to the reranker
# Verdict rule: the variant with the best macro F1 on the gold set's dev split
# (nli+rerank-evidence-first; see eval/gold_metrics.md). Override any of them per run.
VERDICT_ORDER = os.getenv("VERDICT_ORDER", "evidence_first")  # vague_first | evidence_first
VAGUE_BELOW = float(os.getenv("VAGUE_BELOW", "0.05"))     # specificity under this = vague
ENTAIL_AT = float(os.getenv("ENTAIL_AT", "0.2"))          # entailment at or above = support
CONTRADICT_AT = float(os.getenv("CONTRADICT_AT", "0.7"))  # contradiction at or above = conflict
RERANK_AT = None if os.getenv("RERANK_AT", "0").lower() == "none" else float(os.getenv("RERANK_AT", "0"))            # reranker logit at or above = support; "none" disables
