"""Evaluation harness: score every system on each task's held-out test split.

Writes, under eval/ (committed, so changes in the numbers show up in review):
- metrics.json   all numbers, plus which models and data produced them
- metrics.md     the comparison tables
- predictions/<task>.csv   per-row label, prediction and score for each system
                           (row index into the test split; no text, for licensing)

    python -m scripts.evaluate                 # all tasks
    python -m scripts.evaluate --task claims
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import subprocess
from pathlib import Path

import pandas as pd

from esg.eval import datasets, systems
from esg.eval.metrics import binary_metrics, bootstrap_f1_ci

log = logging.getLogger("evaluate")

TASK_TITLES = {
    "claims": "Claim detection: is this sentence an environmental claim?",
    "specificity": "Specificity: is this climate passage specific (figures, targets, actions) rather than vague?",
}


def evaluate_task(task: str) -> tuple[dict, pd.DataFrame]:
    test = datasets.load(task, "test")
    results, preds = {}, pd.DataFrame({"row": range(len(test)), "label": test.label})
    for p in systems.all_systems(task, list(test.text)):
        m = binary_metrics(test.label, p.pred, p.score)
        m["f1_ci95"] = bootstrap_f1_ci(test.label, p.pred)
        m["description"] = p.description
        results[p.system] = m
        preds[f"{p.system}_pred"] = p.pred
        if p.score is not None:
            preds[f"{p.system}_score"] = p.score.round(4)
        log.info("%s / %s: F1 %.3f", task, p.system, m["f1"])
    return results, preds


def model_info(task: str) -> dict | None:
    from esg import config
    path = (config.CLAIM_MODEL_DIR if task == "claims" else config.SPECIFICITY_MODEL_DIR) / "train_meta.json"
    if not path.exists():
        return None
    meta = json.loads(path.read_text())
    return {k: meta.get(k) for k in ("name", "base_model", "train_rows", "validation_rows", "epochs",
                                     "lr", "max_length", "seed", "best_epoch", "train_minutes")}


def git_commit() -> str | None:
    if os.getenv("GIT_COMMIT"):  # set when running in Docker, which has no .git
        return os.environ["GIT_COMMIT"]
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def to_markdown(report: dict) -> str:
    lines = ["# Evaluation results", "",
             f"Generated {report['generated']} by `python -m scripts.evaluate`"
             + (f" at commit `{report['git_commit']}`." if report.get("git_commit") else "."),
             "Positive-class precision, recall and F1 on each dataset's held-out test split; "
             "F1 has a 95% bootstrap interval (1,000 resamples).", ""]
    for task, t in report["tasks"].items():
        lines += [f"## {TASK_TITLES[task]}", "",
                  f"Test set: `{t['dataset']}`, {t['n']} rows, {t['positives']} positive.", "",
                  "| System | What it predicts | Precision | Recall | F1 (95% CI) | Macro F1 | ROC AUC |",
                  "|---|---|---|---|---|---|---|"]
        for name, m in t["systems"].items():
            auc = f"{m['roc_auc']:.3f}" if "roc_auc" in m else "-"
            lo, hi = m["f1_ci95"]
            lines.append(f"| `{name}` | {m['description']} | {m['precision']:.3f} | {m['recall']:.3f} | "
                         f"**{m['f1']:.3f}** ({lo:.2f}-{hi:.2f}) | {m['macro_f1']:.3f} | {auc} |")
        if t.get("model"):
            mi = t["model"]
            lines += ["", f"Fine-tuned model: `{mi['base_model']}`, {mi['train_rows']} training rows, "
                          f"best of {mi['epochs']} epochs on validation (epoch {mi['best_epoch']}), "
                          f"lr {mi['lr']}, max {mi['max_length']} tokens, seed {mi['seed']}, "
                          f"{mi['train_minutes']} min on CPU."]
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", choices=datasets.TASKS, action="append")
    parser.add_argument("--out", type=Path, default=Path("eval"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    out = args.out
    (out / "predictions").mkdir(parents=True, exist_ok=True)
    metrics_path = out / "metrics.json"
    report = json.loads(metrics_path.read_text()) if metrics_path.exists() else {"tasks": {}}
    for task in args.task or datasets.TASKS:
        results, preds = evaluate_task(task)
        test = datasets.load(task, "test")
        report["tasks"][task] = {
            "dataset": datasets.SOURCES[task].repo,
            "n": len(test),
            "positives": int(test.label.sum()),
            "model": model_info(task),
            "systems": results,
        }
        preds.to_csv(out / "predictions" / f"{task}.csv", index=False)
    report["generated"] = dt.date.today().isoformat()
    report["git_commit"] = git_commit()
    metrics_path.write_text(json.dumps(report, indent=2) + "\n")
    (out / "metrics.md").write_text(to_markdown(report), encoding="utf-8")
    log.info("Wrote %s and %s", metrics_path, out / "metrics.md")


if __name__ == "__main__":
    main()
