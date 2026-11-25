"""Greenwashing dashboard: risk per report, and each report's claims with evidence and verdict.

    pip install -r requirements.txt
    API_URL=http://127.0.0.1:8080 streamlit run streamlit_app.py
"""

import streamlit as st

st.set_page_config(page_title="Greenwashing detector", page_icon=":material/eco:", layout="wide")

page = st.navigation(
    [
        st.Page("app_pages/overview.py", title="Overview", icon=":material/leaderboard:", default=True,
                help="Risk score of every analysed report, riskiest first. Pick a report to see its claims."),
        st.Page("app_pages/report.py", title="Report", icon=":material/description:", url_path="report",
                help="One report's environmental claims, each with its verdict, the reason, and the "
                     "passages retrieved as evidence. Filter by verdict or search the text."),
    ],
    position="top",
)
st.title(page.title, anchor=False)
page.run()
