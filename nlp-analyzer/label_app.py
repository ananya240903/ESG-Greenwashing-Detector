"""Hand-label the BRSR gold set: one claim at a time, with its pooled evidence.

    cd nlp-analyzer
    pip install -r requirements-label.txt
    streamlit run label_app.py
    streamlit run label_app.py -- --second-pass   # careful re-label of the test split

Reads eval/gold/items.jsonl (from scripts/export_gold_items.py) and appends each answer to
eval/gold/labels.jsonl, so you can stop and resume at any point; re-saving a claim
replaces its earlier answer.
"""

from __future__ import annotations

import datetime as dt
import re
import sys

import streamlit as st

from esg.eval import gold

st.set_page_config(page_title="BRSR gold labelling", page_icon=":material/fact_check:", layout="wide")

GUIDE = """
**Is it an environmental claim?** A statement by the company about its *own* environmental
performance, actions, policies or commitments. Answer **No** for questions or instructions
from the BRSR form, descriptions of regulations, definitions, and social or governance topics.

**Verdict**, judged only from the passages shown:

- **Substantiated**: at least one passage gives concrete facts (figures, named projects,
  certifications, dates) that back the claim. Figures inside the claim itself do not count
  unless a passage confirms them.
- **Vague**: too general to check. No figures, targets, scope or concrete actions
  ("we are committed to a greener planet").
- **Unsupported**: specific enough to check, but no passage backs it, or one contradicts it.

**Passages that back the claim**: tick every passage that supports it (required for
Substantiated). Passage order is random and says nothing about relevance.
"""
SECOND_PASS = "--second-pass" in sys.argv
STRICT_NOTE = """
**Second pass.** Your first answers are hidden. Take your time: read every passage (about
1.5-2 minutes per claim).

A passage **backs** a claim only when it states the *same specific fact*: the same figure,
project, target, certification or action. A passage on the same topic is not enough. If no
passage clearly backs a checkable claim, choose **Unsupported**.
"""
VERDICT_OPTIONS = {"Substantiated": "substantiated", "Vague": "vague", "Unsupported": "unsupported"}


@st.cache_data
def load_items(mtime: float) -> list[dict]:
    return gold.read_jsonl(gold.ITEMS)


if not gold.ITEMS.exists():
    st.error("Run `python -m scripts.export_gold_items` first.", title="No items to label")
    st.stop()

items = load_items(gold.ITEMS.stat().st_mtime)
labels_path = gold.LABELS_PASS2 if SECOND_PASS else gold.LABELS
if SECOND_PASS:
    keep = set(gold.second_pass_keys())
    items = [it for it in items if it["key"] in keep]
labels = gold.latest_labels(labels_path)
done = sum(1 for it in items if it["key"] in labels)


def first_unlabelled(after: int = -1) -> int:
    n = len(items)
    for step in range(1, n + 1):
        i = (after + step) % n
        if items[i]["key"] not in labels:
            return i
    return max(after, 0)


st.session_state.setdefault("pos", first_unlabelled())

# ---- sidebar: progress and navigation ----
with st.sidebar:
    st.header("Second pass" if SECOND_PASS else "Progress")
    st.progress(done / len(items), text=f"{done} of {len(items)} labelled")
    with st.container(horizontal=True):
        if st.button("Previous", icon=":material/arrow_back:"):
            st.session_state.pos = (st.session_state.pos - 1) % len(items)
        if st.button("Next unlabelled", icon=":material/arrow_forward:"):
            st.session_state.pos = first_unlabelled(st.session_state.pos)
    jump = st.number_input("Go to claim", min_value=1, max_value=len(items),
                           value=st.session_state.pos + 1, step=1)
    if jump - 1 != st.session_state.pos and st.button("Go", icon=":material/move_down:"):
        st.session_state.pos = int(jump) - 1
    with st.expander("Labelling guide", expanded=done == 0, icon=":material/menu_book:"):
        if SECOND_PASS:
            st.markdown(STRICT_NOTE)
        st.markdown(GUIDE)

pos = st.session_state.pos
item = items[pos]
key = item["key"]
saved = labels.get(key)

# ---- the claim ----
where = f"Principle {item['principle']}" if item["principle"] else f"Section {item['section'] or '-'}"
st.caption(f"Claim {pos + 1} of {len(items)} · {item['company']} FY{item['fiscal_year']} · {where} · page {item['page']}"
           + (" · :green[labelled]" if saved else ""))
with st.container(border=True):
    st.markdown(f"#### {item['sentence']}")
with st.expander("Where it appears in the report", icon=":material/article:"):
    context = item["chunk_text"]
    s, e = item["char_start"], item["char_end"]
    st.markdown(re.sub(r"([*_`#])", r"\\\1", context[:s]) + "**" + context[s:e] + "**"
                + re.sub(r"([*_`#])", r"\\\1", context[e:]))

# ---- evidence ----
st.subheader(f"Passages ({len(item['passages'])})")
for p in item["passages"]:
    with st.container(border=True):
        st.markdown(f"**{p['pid']}** · {p['label']}")
        if p["kind"] == "table":
            st.code(p["text"], language=None, wrap_lines=True)
        else:
            st.text(p["text"])

# ---- the answer ----
pids = [p["pid"] for p in item["passages"]]
with st.form(key=f"form_{key}"):
    is_claim = st.segmented_control(
        "Is this an environmental claim the company makes about itself?", ["Yes", "No"],
        default=None if not saved else ("Yes" if saved["is_claim"] else "No"), key=f"claim_{key}")
    verdict = st.segmented_control(
        "Verdict (skip if not a claim)", list(VERDICT_OPTIONS),
        default=next((k for k, v in VERDICT_OPTIONS.items() if saved and saved.get("verdict") == v), None),
        key=f"verdict_{key}")
    supporting = st.pills("Passages that back the claim", pids, selection_mode="multi",
                          default=[p for p in (saved or {}).get("supporting", []) if p in pids],
                          key=f"support_{key}")
    note = st.text_input("Note (optional)", value=(saved or {}).get("note", ""), key=f"note_{key}")
    submitted = st.form_submit_button("Save and next", type="primary", icon=":material/save:")

if submitted:
    problem = None
    if is_claim is None:
        problem = "Say whether this is an environmental claim."
    elif is_claim == "Yes" and verdict is None:
        problem = "Choose a verdict."
    elif is_claim == "Yes" and verdict == "Substantiated" and not supporting:
        problem = "Tick the passages that back a substantiated claim."
    if problem:
        st.warning(problem, title="Not saved")
    else:
        gold.append_label(path=labels_path, label={
            "key": key,
            "is_claim": is_claim == "Yes",
            "verdict": VERDICT_OPTIONS[verdict] if is_claim == "Yes" else None,
            "supporting": sorted(supporting) if is_claim == "Yes" else [],
            "note": note.strip(),
            "labelled_at": dt.datetime.now().isoformat(timespec="seconds"),
        })
        labels[key] = True  # so first_unlabelled skips this item
        st.session_state.pos = first_unlabelled(pos)
        st.rerun()
