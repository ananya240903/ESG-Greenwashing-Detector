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

names = {r["reportId"]: api.report_name(r) for r in reports}
st.session_state.setdefault("report", reports[0]["reportId"])
report_id = st.selectbox("Report", list(names), format_func=names.get, key="report", bind="query-params")

data = api.report_claims(report_id)
risk = data.get("risk") or {}
claims = data["claims"]

with st.container(horizontal=True):
    st.metric("Risk score", f"{risk.get('riskScore', 0):.1f}", border=True,
              help="Prominence-weighted share of claims that are vague or unsupported (0-100).")
    st.metric("Claims", len(claims), border=True)
    for key, meta in api.VERDICTS.items():
        st.metric(meta["label"], risk.get(key, 0), border=True)

with st.container(horizontal=True, vertical_alignment="bottom"):
    chosen = st.pills("Verdict", list(api.VERDICTS), selection_mode="multi", default=list(api.VERDICTS),
                      format_func=lambda v: api.VERDICTS[v]["label"], key="verdict_filter")
    query = st.text_input("Search claims", placeholder="e.g. water, renewable, 2030", key="search")

shown = [c for c in claims
         if (c["verdict"] or {}).get("label") in chosen
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
                    st.markdown(f"**#{ev['rank']}** {api.where(ev['location'])}{score}{cited}")
                    if ev["location"]["kind"] == "table":
                        st.code(ev["text"], language=None, wrap_lines=True)
                    else:
                        st.text(ev["text"])
