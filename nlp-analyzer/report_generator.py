"""Bar chart of the FinBERT baseline's average risk score per company, read from Postgres.

    python report_generator.py            # writes esg_report.png
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from esg import db  # noqa: E402

QUERY = """
SELECT r.company || ' ' || r.fiscal_year AS report,
       avg(b.risk_score)                 AS risk_score,
       avg(b.flagged::int) * 100         AS flagged_pct
FROM baseline_scores b
JOIN chunks  c ON c.id = b.chunk_id
JOIN reports r ON r.id = c.report_id
GROUP BY r.company, r.fiscal_year
ORDER BY risk_score DESC
"""


def main() -> None:
    with db.connect(retries=1) as conn:
        rows = conn.execute(QUERY).fetchall()
    if not rows:
        print("No analysed reports yet. Upload one and wait for status ANALYZED.")
        return

    df = pd.DataFrame(rows).set_index("report")
    print(df.round(1).to_string())

    ax = df["risk_score"].plot(
        kind="bar", figsize=(10, 6),
        color=["#c0392b" if x > 50 else "#27ae60" for x in df["risk_score"]],
    )
    ax.axhline(50, color="gray", linestyle="--", label="Warning threshold")
    ax.set_title("Greenwashing risk by report (FinBERT baseline)")
    ax.set_xlabel("")
    ax.set_ylabel("Average chunk risk score (0-100)")
    ax.legend()
    ax.grid(axis="y", linestyle="--", alpha=0.7)
    plt.tight_layout()
    plt.savefig("esg_report.png")
    print("Saved esg_report.png")


if __name__ == "__main__":
    main()
