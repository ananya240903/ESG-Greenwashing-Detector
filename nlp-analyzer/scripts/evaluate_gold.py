"""Score the pipeline against the hand-labelled BRSR gold set.

Writes eval/gold_metrics.json and eval/gold_metrics.md. Needs the database (for the
report passages) and runs the reranker and NLI live, so it takes a few minutes on CPU.

1. Claim extraction: precision of the claim classifier on BRSR sentences.
2. Retrieval: does each system rank a passage the labeller marked as supporting in its
   top 1 / top 3? (Over substantiated claims; rankings frozen at export time, judged by pooling.)
3. Verdicts: three-way accuracy and macro F1 for each system. Thresholds are tuned on the
   dev split only, and every number in the table is on the test split.
4. Specificity on BRSR: how well the specificity score separates vague claims.

    python -m scripts.evaluate_gold
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import logging
import os
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.metrics import cohen_kappa_score, confusion_matrix, f1_score, roc_auc_score

from esg import db
from esg.eval import gold
from esg.eval.metrics import binary_metrics
from esg.retrieval.search import ClaimQuery
from esg.verdict.rules import EvidenceScore, Thresholds, decide
from esg.verdict.verify import Verifier, build_index

log = logging.getLogger("evaluate-gold")
LABELS = list(gold.VERDICTS)
GRID = {
    "vague_below": [0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
    "entail_at": [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
    "contradict_at": [0.7, 0.8, 0.9, 1.01],  # 1.01 = never use contradiction
}
# Rule variants, each tuned on dev over GRID (plus its own reranker grid). The one with the
# best dev macro F1 is selected; the test table reports all of them, so the choice is visible.
FAMILIES = {
    "nli-vague-first": {"order": "vague_first", "rerank_at": [None],
                        "what": "Vague check first, then NLI"},
    "nli-evidence-first": {"order": "evidence_first", "rerank_at": [None],
                           "what": "NLI evidence check first, then vague"},
    "nli+rerank-evidence-first": {"order": "evidence_first", "rerank_at": [-2.0, 0.0, 2.0, 4.0, 6.0, 8.0],
                                  "what": "Evidence first; NLI or reranker relevance counts as support"},
}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (float(c - h), float(c + h))


def verdict_metrics(y_true, y_pred, seed: int = 0) -> dict:
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    per_class = f1_score(y_true, y_pred, labels=LABELS, average=None, zero_division=0)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(1000):
        i = rng.integers(0, len(y_true), len(y_true))
        boots.append(f1_score(y_true[i], y_pred[i], labels=LABELS, average="macro", zero_division=0))
    flag_true = y_true != "substantiated"
    flag_pred = y_pred != "substantiated"
    return {
        "n": int(len(y_true)),
        "accuracy": float((y_true == y_pred).mean()),
        "macro_f1": float(f1_score(y_true, y_pred, labels=LABELS, average="macro", zero_division=0)),
        "macro_f1_ci95": [float(x) for x in np.quantile(boots, [0.025, 0.975])],
        "f1_per_class": {lab: float(f) for lab, f in zip(LABELS, per_class)},
        "flag": binary_metrics(flag_true, flag_pred),  # vague or unsupported vs substantiated
        "confusion": confusion_matrix(y_true, y_pred, labels=LABELS).tolist(),
    }


def retrieval_metrics(items: dict[str, dict], claims: list[gold.GoldClaim]) -> dict:
    scored = [c for c in claims if c.verdict == "substantiated" and c.supporting_seqs]
    out = {}
    for system in ("bm25", "vector", "hybrid", "hybrid_rerank"):
        hit1 = hit3 = rr = 0.0
        for c in scored:
            ranking = items[c.key]["systems"][system]
            ranks = [r for r, seq in enumerate(ranking, 1) if seq in c.supporting_seqs]
            hit1 += bool(ranks and ranks[0] == 1)
            hit3 += bool(ranks and ranks[0] <= 3)
            rr += 1 / ranks[0] if ranks else 0
        n = len(scored) or 1
        out[system] = {"n": len(scored), "hit@1": hit1 / n, "hit@3": hit3 / n, "mrr@3": rr / n}
    return out


CACHE = Path("eval/.gold_scores_cache.json")  # not committed; delete to force a re-run


def score_claims(claims: list[gold.GoldClaim], verifier: Verifier, use_cache: bool = False) -> dict[str, dict]:
    """Live evidence + NLI scores for every gold claim, plus the baseline flag of its chunk."""
    stamp = f"{verifier.retriever.reranker.name}|{verifier.nli.name}"
    if use_cache and CACHE.exists():
        cached = json.loads(CACHE.read_text())
        if cached["models"] == stamp and set(cached["scores"]) >= {c.key for c in claims}:
            log.info("Using cached evidence scores from %s", CACHE)
            return {k: {"evidence": [EvidenceScore(**e) for e in v["evidence"]],
                        "baseline_flagged": v["baseline_flagged"]} for k, v in cached["scores"].items()}
    conn = db.connect()
    out = {}
    by_report = defaultdict(list)
    for c in claims:
        by_report[(c.company, c.fiscal_year)].append(c)
    for (company, fy), rows in by_report.items():
        report = conn.execute("SELECT id FROM reports WHERE company = %s AND fiscal_year = %s",
                              (company, fy)).fetchone()
        if report is None:
            raise SystemExit(f"{company} FY{fy} is not in the database; upload it first")
        passages = db.report_passages(conn, report["id"])
        seq_to_id = {p["seq"]: p["id"] for p in passages}
        flagged = {r["seq"]: r["flagged"] for r in conn.execute(
            """SELECT ch.seq, b.flagged FROM baseline_scores b JOIN chunks ch ON ch.id = b.chunk_id
               WHERE ch.report_id = %s""", (report["id"],)).fetchall()}
        queries = [ClaimQuery(seq_to_id[c.chunk_seq], c.sentence, c.char_start, c.char_end) for c in rows]
        scored = verifier.score_evidence(queries, build_index(passages))
        for c, row in zip(rows, scored):
            out[c.key] = {"evidence": [s for _, s in row], "baseline_flagged": bool(flagged.get(c.chunk_seq))}
        log.info("%s FY%s: scored %d claims", company, fy, len(rows))
    CACHE.write_text(json.dumps({"models": stamp, "scores": {
        k: {"evidence": [vars(e) for e in v["evidence"]], "baseline_flagged": v["baseline_flagged"]}
        for k, v in out.items()}}))
    return out


def describe(th: Thresholds) -> str:
    parts = [f"vague < {th.vague_below}", f"entail ≥ {th.entail_at}",
             "no contradiction" if th.contradict_at > 1 else f"contradict ≥ {th.contradict_at}"]
    if th.rerank_at is not None:
        parts.append(f"rerank ≥ {th.rerank_at:g}")
    return ", ".join(parts)


def tune(claims, spec, scores, order: str, rerank_grid) -> tuple[Thresholds, float]:
    best, best_f1 = None, -1.0
    for v, e, k, r in itertools.product(*GRID.values(), rerank_grid):
        th = Thresholds(v, e, k, rerank_at=r, order=order)
        pred = [decide(spec[c.key], scores[c.key]["evidence"], th).label for c in claims]
        f1 = f1_score([c.verdict for c in claims], pred, labels=LABELS, average="macro", zero_division=0)
        if f1 > best_f1 + 1e-9:
            best, best_f1 = th, f1
    return best, best_f1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("eval"))
    parser.add_argument("--cached", action="store_true",
                        help="reuse evidence scores from the last run (same models) instead of re-running them")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    items = {it["key"]: it for it in gold.read_jsonl(gold.ITEMS)}
    pass1, pass2 = gold.latest_labels(), gold.latest_labels(gold.LABELS_PASS2)
    labelled = gold.load_gold(overrides_path=gold.LABELS_PASS2 if pass2 else None)
    if not labelled:
        raise SystemExit(f"No labels in {gold.LABELS} yet; run the labelling app first")
    claims = [c for c in labelled if c.is_claim]
    dev = [c for c in claims if c.split == "dev"]
    test = [c for c in claims if c.split == "test"]
    log.info("%d labelled, %d real claims (%d dev / %d test)", len(labelled), len(claims), len(dev), len(test))

    report = {"generated": dt.date.today().isoformat(), "git_commit": os.getenv("GIT_COMMIT"),
              "labelled": len(labelled), "claims": len(claims), "dev": len(dev), "test": len(test),
              "verdict_counts": dict(Counter(c.verdict for c in claims)),
              "second_pass": len(pass2)}

    # 0. Consistency between the fast first pass and the careful second pass
    if pass2:
        def answer(lab):
            return lab["verdict"] if lab["is_claim"] else "not a claim"
        keys = sorted(pass2)
        a, b = [answer(pass1[k]) for k in keys], [answer(pass2[k]) for k in keys]
        report["agreement"] = {"n": len(keys), "same_answer": sum(x == y for x, y in zip(a, b)) / len(keys),
                               "cohen_kappa": float(cohen_kappa_score(a, b)),
                               "changes": {f"{x} -> {y}": n for (x, y), n in Counter(zip(a, b)).most_common()
                                           if x != y}}

    # 1. Claim extraction precision on BRSR
    k = sum(c.is_claim for c in labelled)
    by_company = defaultdict(lambda: [0, 0])
    for c in labelled:
        by_company[c.company][0] += c.is_claim
        by_company[c.company][1] += 1
    report["claim_precision"] = {"precision": k / len(labelled), "ci95": wilson(k, len(labelled)),
                                 "by_company": {co: v[0] / v[1] for co, v in sorted(by_company.items())}}

    # 2. Retrieval
    report["retrieval"] = retrieval_metrics(items, claims)

    # 3. Verdicts
    verifier = Verifier()
    scores = score_claims(claims, verifier, use_cache=args.cached)
    spec = {c.key: items[c.key]["specificity_score"] for c in claims}
    y_test = [c.verdict for c in test]
    majority = Counter(c.verdict for c in dev).most_common(1)[0][0]
    default = Thresholds(0.5, 0.5, 0.8, rerank_at=None, order="vague_first")
    tuned = {}
    for name, fam in FAMILIES.items():
        tuned[name] = tune(dev, spec, scores, fam["order"], fam["rerank_at"])
        log.info("%s: dev macro F1 %.3f with %s", name, tuned[name][1], describe(tuned[name][0]))
    selected = max(tuned, key=lambda n: tuned[n][1])

    def predict(th):
        return [decide(spec[c.key], scores[c.key]["evidence"], th).label for c in test]

    systems = {
        "majority": ("Always the most common dev label", [majority] * len(test)),
        "finbert-flag": ("Old tool: chunk flagged = vague, else substantiated",
                         ["vague" if scores[c.key]["baseline_flagged"] else "substantiated" for c in test]),
        "specificity-only": ("Specificity < 0.5 = vague, else substantiated (no evidence)",
                             ["vague" if spec[c.key] < 0.5 else "substantiated" for c in test]),
        "nli-default": ("Vague check first, then NLI; untuned (" + describe(default) + ")", predict(default)),
    }
    for name, (th, dev_f1) in tuned.items():
        mark = " **(selected on dev)**" if name == selected else ""
        systems[name] = (f"{FAMILIES[name]['what']}; tuned on dev ({describe(th)}), dev F1 {dev_f1:.2f}{mark}",
                         predict(th))
    report["verdicts"] = {name: {"description": d, **verdict_metrics(y_test, pred)} for name, (d, pred) in systems.items()}
    report["selected"] = selected
    report["tuned_thresholds"] = {name: {"vague_below": th.vague_below, "entail_at": th.entail_at,
                                         "contradict_at": th.contradict_at, "rerank_at": th.rerank_at,
                                         "order": th.order, "dev_macro_f1": f1}
                                  for name, (th, f1) in tuned.items()}

    # Diagnostics over all claims: how well does each evidence signal separate substantiated
    # from unsupported claims? (Not used for any choice above.)
    checkable = [c for c in claims if c.verdict in ("substantiated", "unsupported")]
    yc = [c.verdict == "substantiated" for c in checkable]
    if len(set(yc)) == 2:
        ent = [max((e.entailment for e in scores[c.key]["evidence"]), default=0) for c in checkable]
        rr = [max((e.rerank for e in scores[c.key]["evidence"] if e.rerank is not None), default=-20) for c in checkable]
        report["support_signal_auc"] = {"max_entailment": float(roc_auc_score(yc, ent)),
                                        "max_rerank": float(roc_auc_score(yc, rr)), "n": len(checkable)}
    sel_th = tuned[selected][0]
    report["models"] = {"rerank": verifier.retriever.reranker.name, "nli": verifier.nli.name}

    # 4. Specificity on BRSR: vague vs checkable (substantiated or unsupported)
    y = np.array([c.verdict != "vague" for c in claims], dtype=int)
    s = np.array([spec[c.key] for c in claims])
    if len(set(y)) == 2:
        report["specificity_on_brsr"] = {"roc_auc": float(roc_auc_score(y, s)),
                                         "at_0.5": binary_metrics(y, s >= 0.5),
                                         f"at_{sel_th.vague_below}": binary_metrics(y, s >= sel_th.vague_below)}

    (args.out / "gold_metrics.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.out / "gold_metrics.md").write_text(to_markdown(report), encoding="utf-8")
    log.info("Wrote %s", args.out / "gold_metrics.md")


def to_markdown(r: dict) -> str:
    cp = r["claim_precision"]
    lines = [
        "# Gold-set results (BRSR)", "",
        f"Generated {r['generated']} by `python -m scripts.evaluate_gold`"
        + (f" at commit `{r['git_commit']}`." if r.get("git_commit") else "."),
        f"{r['labelled']} hand-labelled sentences from five FY2023-24 BRSRs; {r['claims']} are real "
        f"environmental claims ({r['dev']} dev / {r['test']} test). Verdicts: "
        + ", ".join(f"{k} {v}" for k, v in sorted(r["verdict_counts"].items())) + ".", "",
    ]
    if r.get("agreement"):
        ag = r["agreement"]
        lines += [
            "## Label quality", "",
            "All labels come from one person. The first pass covered all 200 sentences; the "
            f"{ag['n']} test-split claims were then labelled again with a stricter guide (a passage backs "
            "a claim only if it states the same specific fact) and the first answers hidden. Both passes "
            "were fast, at a median of 16 seconds per claim, so the labels are consistent but were not "
            "checked carefully against every passage. Test numbers below use the second pass; thresholds "
            "are tuned on the first-pass dev labels.", "",
            f"Agreement between the two passes: **{ag['same_answer']:.0%}** same answer, Cohen's kappa "
            f"**{ag['cohen_kappa']:.2f}** (consistency, not accuracy). Most common changes: "
            + ", ".join(f"{k} ({v})" for k, v in list(ag["changes"].items())[:5]) + ".", "",
        ]
    lines += [
        "## Claim extraction on BRSR", "",
        f"Precision **{cp['precision']:.3f}** (95% CI {cp['ci95'][0]:.2f}-{cp['ci95'][1]:.2f}): the share "
        "of sentences the claim classifier picked that are real environmental claims. By company: "
        + ", ".join(f"{co} {p:.2f}" for co, p in cp["by_company"].items()) + ".", "",
        "## Evidence retrieval", "",
        f"Over the {r['retrieval']['bm25']['n']} substantiated claims: is a passage the labeller marked as "
        "supporting ranked first (hit@1) or in the top 3 (hit@3)?", "",
        "| System | Hit@1 | Hit@3 | MRR@3 |", "|---|---|---|---|",
    ]
    for name, m in r["retrieval"].items():
        lines.append(f"| `{name}` | {m['hit@1']:.3f} | {m['hit@3']:.3f} | {m['mrr@3']:.3f} |")
    lines += ["", "Rankings are judged by pooling: the labeller saw the union of every system's top 3. "
              "Only `hybrid_rerank` can return the rest of the claim's own passage.", "",
              f"## Verdicts (test split, {r['test']} claims)", "",
              "| System | What it does | Accuracy | Macro F1 (95% CI) | F1 substantiated / vague / unsupported | Flag F1 |",
              "|---|---|---|---|---|---|"]
    for name, m in r["verdicts"].items():
        pc = m["f1_per_class"]
        lo, hi = m["macro_f1_ci95"]
        lines.append(f"| `{name}` | {m['description']} | {m['accuracy']:.3f} | **{m['macro_f1']:.3f}** "
                     f"({lo:.2f}-{hi:.2f}) | {pc['substantiated']:.2f} / {pc['vague']:.2f} / "
                     f"{pc['unsupported']:.2f} | {m['flag']['f1']:.3f} |")
    sel = r["selected"]
    cm = r["verdicts"][sel]["confusion"]
    lines += ["", "Flag F1: vague or unsupported (a greenwashing flag) against substantiated. "
              "Each `nli-*` variant is tuned on the dev split only; the variant with the best dev score is "
              f"selected, and every row is scored on the test split. Models: `{r['models']['rerank']}`, "
              f"`{r['models']['nli']}`.", ""]
    if "support_signal_auc" in r:
        a = r["support_signal_auc"]
        lines += [f"How well each evidence signal separates substantiated from unsupported claims "
                  f"({a['n']} claims, ROC AUC): NLI max entailment {a['max_entailment']:.3f}, "
                  f"reranker max relevance {a['max_rerank']:.3f}.", ""]
    lines += [f"Confusion matrix for `{sel}` (rows = gold, columns = predicted):", "",
              "| | substantiated | vague | unsupported |", "|---|---|---|---|"]
    for lab, row in zip(LABELS, cm):
        lines.append(f"| **{lab}** | " + " | ".join(map(str, row)) + " |")
    if "specificity_on_brsr" in r:
        s = r["specificity_on_brsr"]
        tuned_key = next(k for k in s if k.startswith("at_") and k != "at_0.5")
        lines += ["", "## Specificity on BRSR sentences", "",
                  f"ROC AUC **{s['roc_auc']:.3f}** for telling checkable claims (substantiated or unsupported) "
                  f"from vague ones. At the default 0.5 cut-off, F1 {s['at_0.5']['f1']:.3f}; at the tuned "
                  f"{tuned_key[3:]}, F1 {s[tuned_key]['f1']:.3f}."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
