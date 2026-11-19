# Evaluation results

Generated 2026-11-19 by `python -m scripts.evaluate` at commit `38f2f73`.
Positive-class precision, recall and F1 on each dataset's held-out test split; F1 has a 95% bootstrap interval (1,000 resamples).

## Claim detection: is this sentence an environmental claim?

Test set: `climatebert/environmental_claims`, 265 rows, 67 positive.

| System | What it predicts | Precision | Recall | F1 (95% CI) | Macro F1 | ROC AUC |
|---|---|---|---|---|---|---|
| `finbert-esg` | FinBERT-ESG top label is Environmental | 0.463 | 0.940 | **0.621** (0.54-0.69) | 0.693 | 0.852 |
| `claims-distilroberta-base-climate-f` | Fine-tuned climatebert/distilroberta-base-climate-f | 0.775 | 0.925 | **0.844** (0.78-0.90) | 0.892 | 0.970 |

Fine-tuned model: `climatebert/distilroberta-base-climate-f`, 2117 training rows, best of 4 epochs on validation (epoch 2), lr 3e-05, max 128 tokens, seed 42, 13.8 min on CPU.

## Specificity: is this climate passage specific (figures, targets, actions) rather than vague?

Test set: `climatebert/climate_specificity`, 320 rows, 123 positive.

| System | What it predicts | Precision | Recall | F1 (95% CI) | Macro F1 | ROC AUC |
|---|---|---|---|---|---|---|
| `finbert-flag` | Old tool's flag (vague and hyped) = not specific | 0.377 | 0.959 | **0.541** (0.48-0.59) | 0.280 | 0.606 |
| `finbert-vague` | FinBERT-ESG unsure (None or < 0.7) = not specific | 0.353 | 0.724 | **0.475** (0.41-0.53) | 0.366 | 0.604 |
| `specificity-distilroberta-base-climate-f` | Fine-tuned climatebert/distilroberta-base-climate-f | 0.806 | 0.675 | **0.735** (0.66-0.79) | 0.795 | 0.880 |

Fine-tuned model: `climatebert/distilroberta-base-climate-f`, 850 training rows, best of 5 epochs on validation (epoch 4), lr 3e-05, max 256 tokens, seed 42, 24.6 min on CPU.
