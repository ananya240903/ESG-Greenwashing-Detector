"""Split handling, with the downloads stubbed out."""

import pandas as pd
import pytest

from esg.eval import datasets


@pytest.fixture
def fake_download(monkeypatch):
    def download(task, split):
        n = 200 if split == "train" else 40
        return pd.DataFrame({"text": [f"{task}-{split}-{i}" for i in range(n)],
                             "label": [i % 2 for i in range(n)]})
    monkeypatch.setattr(datasets, "_download", download)


def test_carved_validation_never_overlaps_train(fake_download):
    # climate_specificity publishes no validation split, so one is held out of train.
    train = datasets.load("specificity", "train")
    val = datasets.load("specificity", "validation")
    assert not set(train.text) & set(val.text)
    assert len(train) + len(val) == 200
    assert len(val) == 30  # 15%
    assert val.label.mean() == pytest.approx(0.5)  # stratified


def test_holdout_is_the_same_every_time(fake_download):
    assert list(datasets.load("specificity", "validation").text) == \
           list(datasets.load("specificity", "validation").text)


def test_published_splits_are_used_as_is(fake_download):
    assert len(datasets.load("claims", "train")) == 200
    assert len(datasets.load("claims", "validation")) == 40
    assert len(datasets.load("specificity", "test")) == 40


def test_unknown_split_is_rejected(fake_download):
    with pytest.raises(ValueError):
        datasets.load("claims", "dev")
