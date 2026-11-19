import pytest

from esg.eval.metrics import binary_metrics, bootstrap_f1_ci


def test_binary_metrics_on_a_hand_checked_case():
    # 2 TP, 1 FP, 1 FN, 2 TN
    m = binary_metrics([1, 1, 1, 0, 0, 0], [1, 1, 0, 1, 0, 0], y_score=[.9, .8, .4, .6, .2, .1])
    assert m["precision"] == pytest.approx(2 / 3)
    assert m["recall"] == pytest.approx(2 / 3)
    assert m["f1"] == pytest.approx(2 / 3)
    assert m["accuracy"] == pytest.approx(4 / 6)
    assert m["roc_auc"] == pytest.approx(8 / 9)
    assert (m["n"], m["positives"]) == (6, 3)


def test_predicting_no_positives_scores_zero_not_an_error():
    m = binary_metrics([1, 0, 0], [0, 0, 0])
    assert m["f1"] == 0 and m["precision"] == 0


def test_bootstrap_interval_brackets_the_point_estimate():
    y = [1, 0] * 50
    pred = [1, 0] * 40 + [0, 1] * 10
    f1 = binary_metrics(y, pred)["f1"]
    lo, hi = bootstrap_f1_ci(y, pred, n_resamples=300)
    assert lo < f1 < hi
    assert bootstrap_f1_ci(y, pred, n_resamples=300) == (lo, hi)  # seeded: reproducible
