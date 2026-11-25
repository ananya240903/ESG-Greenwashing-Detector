import pandas as pd
import streamlit as st

import api

st.caption("How much of each BRSR's environmental messaging is vague or unsupported by its own report.")
st.info(
    "Verdicts come from an NLI model and explicit rules that score a macro F1 of about 0.4 on a "
    "hand-labelled gold set, and they lean towards *substantiated*. Use the scores to compare "
    "reports and to find claims worth reading, not as findings about a company.",
    title="Read these scores with care", icon=":material/info:",
)

try:
    rows = api.risk()
except api.ApiError as exc:
    st.error(str(exc), title="No data")
    st.stop()
if not rows:
    st.warning("No report has been analysed yet. Upload a BRSR PDF to the API first.", title="No reports")
    st.stop()

df = pd.DataFrame(rows)
df["report"] = df.apply(api.report_name, axis=1)
total = int(df["claims"].sum())
flagged = int((df["vague"] + df["unsupported"]).sum())

with st.container(horizontal=True):
    st.metric("Reports analysed", len(df), border=True)
    st.metric("Environmental claims", f"{total:,}", border=True)
    st.metric("Vague or unsupported", f"{flagged / total:.0%}", border=True,
              help="Unweighted share across all reports; the risk score weights Section B claims 1.5x.")

left, right = st.columns([2, 3])
with left, st.container(border=True):
    st.markdown("**Risk score by report**")
    st.bar_chart(df, x="report", y="riskScore", horizontal=True, sort="-riskScore", color="#2a78d6",
                 x_label="Risk score (0-100)", y_label="",
                 alt="Horizontal bars of risk score per report, highest first: "
                     + ", ".join(f"{r} {s:.0f}" for r, s in zip(df["report"], df["riskScore"])))
with right, st.container(border=True):
    st.markdown("**Claims by verdict** · select a row to open the report")
    event = st.dataframe(
        df[["report", "riskScore", "claims", "substantiated", "vague", "unsupported"]],
        hide_index=True, on_select="rerun", selection_mode="single-row", key="risk_table",
        column_config={
            "report": st.column_config.TextColumn("Report"),
            "riskScore": st.column_config.ProgressColumn("Risk score", min_value=0, max_value=100, format="%.1f"),
            "claims": st.column_config.NumberColumn("Claims"),
            "substantiated": st.column_config.NumberColumn("Substantiated"),
            "vague": st.column_config.NumberColumn("Vague"),
            "unsupported": st.column_config.NumberColumn("Unsupported"),
        },
        alt="Table of reports with risk score and claim counts by verdict",
    )
    if event.selection.rows:
        chosen = int(df.iloc[event.selection.rows[0]]["reportId"])
        st.switch_page("app_pages/report.py", query_params={"report": str(chosen)})

st.caption("Risk score = 100 × (prominence of vague + unsupported claims) / (prominence of all claims). "
           "Claims in Section B, where the director's statement and headline commitments sit, count 1.5×.")
