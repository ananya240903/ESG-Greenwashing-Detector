import math

import streamlit as st

import api

PAGE_SIZE = 20

try:
    reports = api.risk()
except api.ApiError as exc:
    st.error(str(exc), title="No data")
    st.stop()
if not reports:
    st.warning("No report has been analysed yet.", title="No reports")
    st.stop()

# A bound select box puts the option's displayed text in the URL, so the options are report
# names: ?report=Wipro FY2024 (from the Overview page, or a shared link) selects that report.
# Do not seed st.session_state["report"]: on first load that would win over the URL. With no
# ?report= the first (riskiest) report is shown.
ids = {api.report_name(r): r["reportId"] for r in reports}
report_name = st.selectbox("Report", list(ids), key="report", bind="query-params")
report_id = ids[report_name]

data = api.report_claims(report_id)
risk = data.get("risk") or {}
claims = data["claims"]

with st.container(horizontal=True):
    st.metric("Risk score", f"{risk.get('riskScore', 0):.1f}", border=True,
              help="Prominence-weighted share of claims that are vague or unsupported (0-100).")
    st.metric("Claims", len(claims), border=True)
    for key, meta in api.VERDICTS.items():
        st.metric(meta["label"], risk.get(key, 0), border=True)

with st.expander("Claims by topic", icon=":material/category:"):
    rows = []
    for key, meta in api.TOPICS.items():
        tagged = [c for c in claims if key in (c.get("topics") or [])]
        counts = {v: sum((c["verdict"] or {}).get("label") == v for c in tagged) for v in api.VERDICTS}
        rows.append({"Topic": meta["label"], "BRSR Core attribute": meta["brsr_core"] or "",
                     "Claims": len(tagged), **{api.VERDICTS[v]["label"]: n for v, n in counts.items()},
                     "Vague or unsupported": (counts["vague"] + counts["unsupported"]) / len(tagged) if tagged else None})
    st.dataframe(rows, hide_index=True, alt="Claims per BRSR topic, with counts by verdict",
                 column_config={"Vague or unsupported": st.column_config.ProgressColumn(
                     "Vague or unsupported", min_value=0, max_value=1, format="percent")})
    st.caption("Topics are tagged by keyword and can overlap. GHG, water, energy and waste are SEBI BRSR Core "
               "attributes, which listed companies must have independently assured.")

with st.container(horizontal=True, vertical_alignment="bottom"):
    chosen = st.pills("Verdict", list(api.VERDICTS), selection_mode="multi", default=list(api.VERDICTS),
                      format_func=lambda v: api.VERDICTS[v]["label"], key="verdict_filter")
    topic = st.selectbox("Topic", [None, *api.TOPICS], format_func=lambda t: "All topics" if t is None
                         else api.TOPICS[t]["label"], key="topic_filter")
    query = st.text_input("Search claims", placeholder="e.g. water, renewable, 2030", key="search")

shown = [c for c in claims
         if (c["verdict"] or {}).get("label") in chosen
         and (topic is None or topic in (c.get("topics") or []))
         and (not query or query.lower() in c["sentence"].lower())]
pages = max(1, math.ceil(len(shown) / PAGE_SIZE))
page = st.number_input("Page", min_value=1, max_value=pages, value=1, step=1, key=f"page_{report_id}") if pages > 1 else 1
st.caption(f"{len(shown)} of {len(claims)} claims" + (f" · page {page} of {pages}" if pages > 1 else ""))

for claim in shown[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]:
    verdict = claim["verdict"] or {}
    meta = api.VERDICTS.get(verdict.get("label"), {"label": "No verdict", "color": "gray", "icon": None})
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.badge(meta["label"], icon=meta["icon"], color=meta["color"])
            for t in claim.get("topics") or []:
                core = api.TOPICS[t]["brsr_core"]
                st.badge(api.TOPICS[t]["label"], color="blue" if core else "gray",
                         help=f"SEBI BRSR Core attribute: {core}" if core else None)
            st.caption(api.where(claim["location"]))
        st.markdown(f"**{claim['sentence']}**")
        if verdict.get("reason"):
            st.caption(verdict["reason"])
        spec = claim.get("specificityScore")
        st.caption(f"Claim confidence {claim['claimScore']:.2f} · specificity "
                   f"{'-' if spec is None else f'{spec:.2f}'} · prominence {claim.get('prominence') or 1:g}")
        if claim["evidence"]:
            with st.expander(f"Evidence ({len(claim['evidence'])} passages)", icon=":material/plagiarism:"):
                for ev in claim["evidence"]:
                    cited = " · :green-badge[:material/check: cited]" if ev["cited"] else ""
                    score = "" if ev["rerankScore"] is None else f" · relevance {ev['rerankScore']:.1f}"
                    own = " · rest of the claim's own passage" if ev.get("ownPassage") else ""
                    st.markdown(f"**#{ev['rank']}** {api.where(ev['location'])}{own}{score}{cited}")
                    # The models judged the claim's own passage without the claim in it; show it that way.
                    text = ev["text"].replace(claim["sentence"], "[…claim…]") if ev.get("ownPassage") else ev["text"]
                    if ev["location"]["kind"] == "table":
                        st.code(text, language=None, wrap_lines=True)
                    else:
                        st.text(text)
