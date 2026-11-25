"""Labelled datasets for training and evaluation, all as DataFrames with `text` and `label`.

Public data (ClimateBERT, CC BY-NC-SA 4.0, research use):
- claims:      climatebert/environmental_claims - sentences from annual and sustainability
               reports; 1 = an environmental claim (Stammbach et al., 2022).
- specificity: climatebert/climate_specificity - climate paragraphs from corporate
               reports; 1 = specific (concrete targets, figures, actions), 0 = vague.

The files are pinned to a dataset revision, so numbers are reproducible.
The specificity dataset has no validation split, so a fixed 15% of its train split
is held out (stratified, seed 42) for model selection.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import pandas as pd

TASKS = ("claims", "specificity")


@dataclass(frozen=True)
class Source:
    repo: str
    revision: str
    files: dict[str, str]          # split -> path inside the repo
    positive_name: str             # what label 1 means, for reports


SOURCES = {
    "claims": Source(
        repo="climatebert/environmental_claims",
        revision="main",
        files={
            "train": "data/train-00000-of-00001-98aa5228a06a17d0.parquet",
            "validation": "data/validation-00000-of-00001-2553e47d408fab28.parquet",
            "test": "data/test-00000-of-00001-79fd931297fff765.parquet",
        },
        positive_name="environmental claim",
    ),
    "specificity": Source(
        repo="climatebert/climate_specificity",
        revision="main",
        files={
            "train": "data/train-00000-of-00001-298fad749f8929f7.parquet",
            "test": "data/test-00000-of-00001-2588e03729a1bfe7.parquet",
        },
        positive_name="specific",
    ),
}

HOLDOUT_FRACTION = 0.15
SEED = 42


@lru_cache(maxsize=None)
def _download(task: str, split: str) -> pd.DataFrame:
    from huggingface_hub import hf_hub_download

    src = SOURCES[task]
    path = hf_hub_download(src.repo, src.files[split], repo_type="dataset", revision=src.revision)
    df = pd.read_parquet(path)[["text", "label"]]
    df["text"] = df["text"].astype(str).str.strip()
    df["label"] = df["label"].astype(int)
    return df.reset_index(drop=True)


def load(task: str, split: str) -> pd.DataFrame:
    """split: train | validation | test."""
    if task not in SOURCES:
        raise ValueError(f"unknown task {task!r}; expected one of {TASKS}")
    src = SOURCES[task]
    if split not in ("train", "validation", "test"):
        raise ValueError(f"unknown split {split!r}")
    if split == "test" or "validation" in src.files:
        return _download(task, split).copy()

    # No published validation split: carve one out of train, the same way every time.
    from sklearn.model_selection import train_test_split

    full = _download(task, "train")
    train, val = train_test_split(full, test_size=HOLDOUT_FRACTION, random_state=SEED,
                                  stratify=full["label"])
    return (train if split == "train" else val).reset_index(drop=True)
