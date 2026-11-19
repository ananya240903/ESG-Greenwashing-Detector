"""Fine-tune a binary classifier for one task (claims | specificity).

Trains on the task's train split, picks the epoch with the best validation F1,
and saves that model with train_meta.json (settings, data sizes, per-epoch scores).
CPU is fine: about 10-15 minutes per task on 6 cores.

    python -m scripts.train_classifier --task claims
    python -m scripts.train_classifier --task specificity
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import shutil
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader
from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                          get_linear_schedule_with_warmup)

from esg import config
from esg.claims.classifier import TextClassifier
from esg.eval import datasets
from esg.eval.metrics import binary_metrics

log = logging.getLogger("train")

# Settings per task. Specificity texts are paragraphs (p95 ~ 160 words), so they need a
# longer window; the claims data is single sentences (p95 ~ 40 words).
TASK_SETTINGS = {
    "claims": {"max_length": 128, "epochs": 4, "lr": 3e-5, "batch_size": 16},
    "specificity": {"max_length": 256, "epochs": 5, "lr": 3e-5, "batch_size": 16},
}


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", choices=datasets.TASKS, required=True)
    parser.add_argument("--base-model", default=config.CLASSIFIER_BASE_MODEL)
    parser.add_argument("--out", type=Path, help="default: models/<task>")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--lr", type=float)
    parser.add_argument("--limit", type=int, help="train on the first N rows only (smoke test)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    settings = dict(TASK_SETTINGS[args.task])
    settings.update({k: v for k, v in (("epochs", args.epochs), ("lr", args.lr)) if v is not None})
    out = args.out or config.MODELS_DIR / args.task
    set_seed(args.seed)
    torch.set_num_threads(max(1, torch.get_num_threads()))

    train_df = datasets.load(args.task, "train")
    val_df = datasets.load(args.task, "validation")
    if args.limit:
        train_df, val_df = train_df.head(args.limit), val_df.head(max(20, args.limit // 4))
    log.info("%s: %d train / %d validation rows, %.0f%% positive",
             args.task, len(train_df), len(val_df), 100 * train_df.label.mean())

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.base_model, num_labels=2,
        id2label={0: "negative", 1: datasets.SOURCES[args.task].positive_name},
        label2id={"negative": 0, datasets.SOURCES[args.task].positive_name: 1},
    )

    def collate(rows):
        enc = tokenizer([r[0] for r in rows], truncation=True, max_length=settings["max_length"],
                        padding=True, return_tensors="pt")
        enc["labels"] = torch.tensor([r[1] for r in rows])
        return enc

    loader = DataLoader(list(zip(train_df.text, train_df.label)), batch_size=settings["batch_size"],
                        shuffle=True, collate_fn=collate,
                        generator=torch.Generator().manual_seed(args.seed))
    steps = len(loader) * settings["epochs"]
    optimizer = torch.optim.AdamW(model.parameters(), lr=settings["lr"], weight_decay=0.01)
    scheduler = get_linear_schedule_with_warmup(optimizer, int(0.1 * steps), steps)

    tmp = out.with_name(out.name + ".tmp")
    best_f1, history, started = -1.0, [], time.monotonic()
    for epoch in range(1, settings["epochs"] + 1):
        model.train()
        total = 0.0
        for step, batch in enumerate(loader, 1):
            loss = model(**batch).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            total += loss.item()
            if step % 25 == 0:
                log.info("epoch %d step %d/%d loss %.4f", epoch, step, len(loader), total / step)

        model.eval()
        model.save_pretrained(tmp)
        tokenizer.save_pretrained(tmp)
        (tmp / "train_meta.json").write_text(json.dumps({"max_length": settings["max_length"]}))
        probs = TextClassifier(tmp).predict_proba(list(val_df.text))
        val = binary_metrics(val_df.label, probs >= 0.5, probs)
        history.append({"epoch": epoch, "train_loss": total / len(loader), **val})
        log.info("epoch %d: train loss %.4f, val F1 %.3f (P %.3f R %.3f AUC %.3f)", epoch,
                 total / len(loader), val["f1"], val["precision"], val["recall"], val["roc_auc"])
        if val["f1"] > best_f1:
            best_f1 = val["f1"]
            if out.exists():
                shutil.rmtree(out)
            shutil.copytree(tmp, out)

    shutil.rmtree(tmp, ignore_errors=True)
    best = max(history, key=lambda h: h["f1"])
    meta = {
        "name": f"{args.task}-{Path(args.base_model).name}",
        "task": args.task,
        "base_model": args.base_model,
        "dataset": datasets.SOURCES[args.task].repo,
        "train_rows": len(train_df),
        "validation_rows": len(val_df),
        "seed": args.seed,
        **settings,
        "best_epoch": best["epoch"],
        "history": history,
        "train_minutes": round((time.monotonic() - started) / 60, 1),
    }
    (out / "train_meta.json").write_text(json.dumps(meta, indent=2))
    log.info("Saved %s (best epoch %d, val F1 %.3f) in %.1f min",
             out, best["epoch"], best["f1"], meta["train_minutes"])


if __name__ == "__main__":
    main()
