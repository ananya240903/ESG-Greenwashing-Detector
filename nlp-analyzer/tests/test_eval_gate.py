"""Regression gate: re-run the evaluation and fail if the fine-tuned models get worse.

Slow (runs every model over both test sets, a few minutes on CPU), so it is opt-in:

    pytest -m eval

Skipped when the models have not been trained. Floors sit a little under the scores
recorded in eval/metrics.json, so a real regression fails but run-to-run noise does not.
"""

import pytest

from esg import config
from esg.claims.classifier import model_exists

pytestmark = pytest.mark.eval

# task: (minimum F1 for the fine-tuned model, minimum lead over the best baseline)
FLOORS = {
    "claims": (0.80, 0.15),
    "specificity": (0.70, 0.15),
}
MODEL_DIRS = {"claims": config.CLAIM_MODEL_DIR, "specificity": config.SPECIFICITY_MODEL_DIR}


@pytest.mark.parametrize("task", sorted(FLOORS))
def test_fine_tuned_model_meets_floor_and_beats_baseline(task):
    if not model_exists(MODEL_DIRS[task]):
        pytest.skip(f"no trained model in {MODEL_DIRS[task]}")
    from scripts.evaluate import evaluate_task

    results, _ = evaluate_task(task)
    tuned = {k: v for k, v in results.items() if not k.startswith("finbert")}
    baselines = {k: v for k, v in results.items() if k.startswith("finbert")}
    assert len(tuned) == 1 and baselines
    (name, m), = tuned.items()
    best_name, best = max(baselines.items(), key=lambda kv: kv[1]["f1"])
    floor, lead = FLOORS[task]
    assert m["f1"] >= floor, f"{name} F1 {m['f1']:.3f} fell below {floor}"
    assert m["f1"] - best["f1"] >= lead, (
        f"{name} F1 {m['f1']:.3f} leads {best_name} ({best['f1']:.3f}) by less than {lead}")
