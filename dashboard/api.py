"""Client for the ingestor API: the dashboard reads everything through it, never the database."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import streamlit as st

API_URL = os.getenv("API_URL", "http://127.0.0.1:8080").rstrip("/")

VERDICTS = {
    "substantiated": {"label": "Substantiated", "color": "green", "icon": ":material/check_circle:"},
    "vague": {"label": "Vague", "color": "orange", "icon": ":material/help:"},
    "unsupported": {"label": "Unsupported", "color": "red", "icon": ":material/cancel:"},
}


class ApiError(RuntimeError):
    pass


def _get(path: str):
    try:
        with urllib.request.urlopen(f"{API_URL}{path}", timeout=30) as resp:
            return json.load(resp)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ApiError(f"Could not reach the API at {API_URL}: {exc}") from exc


@st.cache_data(ttl=60, show_spinner=False)
def risk() -> list[dict]:
    """Every analysed report with its verdict counts and risk score, riskiest first."""
    return _get("/api/reports/risk")


@st.cache_data(ttl=60, show_spinner=False, max_entries=20)
def report_claims(report_id: int) -> dict:
    """One report's claims, each with its verdict and ranked evidence."""
    return _get(f"/api/reports/{report_id}/claims")


def report_name(r: dict) -> str:
    return f"{r['company']} FY{r['fiscalYear']}"


def where(location: dict) -> str:
    part = f"Principle {location['principle']}" if location.get("principle") else f"Section {location.get('section') or '-'}"
    return f"{location['kind']}, {part}, p. {location['page']}"
