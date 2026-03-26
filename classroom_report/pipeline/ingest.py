"""Parse slides and Excel; compute analytics — used by Streamlit, API, and LangGraph."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Optional

import pandas as pd

from classroom_report.analytics.scoring import assign_tiers, compute_scores, get_top_n
from classroom_report.config import MAX_EXCEL_SIZE_BYTES, MAX_SLIDES_SIZE_BYTES
from classroom_report.parsers.responses import load_responses, normalize_responses


@dataclass
class AnalyticsBundle:
    """DataFrames from a completed analytics pass."""

    responses_df: pd.DataFrame
    question_columns: list[str]
    scores_df: pd.DataFrame
    ranked_df: pd.DataFrame
    top5_df: pd.DataFrame
    tier_counts: dict[str, int]


def parse_slides_bytes(filename: str, data: bytes) -> tuple[str, str]:
    """
    Return (lecture_text, poll_questions_text) from slide bytes.
    filename must include extension (.pptx or .pdf).
    """
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    buf = BytesIO(data)
    buf.name = filename
    if ext == "pptx":
        from classroom_report.parsers.slides_pptx import extract_text_from_pptx, get_poll_slides

        full_text, slides_text = extract_text_from_pptx(buf)
    elif ext == "pdf":
        from classroom_report.parsers.slides_pdf import extract_text_from_pdf, get_poll_slides

        full_text, slides_text = extract_text_from_pdf(buf)
    else:
        return "", ""

    poll_slides = get_poll_slides(slides_text)
    poll_text = "\n\n".join([f"Slide {i}: {t}" for i, t in poll_slides]) if poll_slides else ""
    return full_text, poll_text


def parse_responses_bytes(
    excel_bytes: bytes,
    filename: str = "responses.xlsx",
    answer_key: Optional[str] = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Load Excel bytes and return (df, question_columns). Raises on error."""
    buf = BytesIO(excel_bytes)
    buf.name = filename
    df = load_responses(buf, answer_key=answer_key)
    df, q_cols = normalize_responses(df)
    return df, q_cols


def run_analytics(df: pd.DataFrame, question_columns: list[str]) -> AnalyticsBundle:
    """Compute scores, tiers, top 5, and tier counts."""
    scores_df = compute_scores(df, question_columns)
    ranked_df = assign_tiers(scores_df)
    top5_df = get_top_n(ranked_df, 5)
    tier_counts = ranked_df["tier"].value_counts().to_dict() if "tier" in ranked_df.columns else {}
    return AnalyticsBundle(
        responses_df=df,
        question_columns=question_columns,
        scores_df=scores_df,
        ranked_df=ranked_df,
        top5_df=top5_df,
        tier_counts=tier_counts,
    )


def assert_slides_size(num_bytes: int) -> None:
    if num_bytes > MAX_SLIDES_SIZE_BYTES:
        raise ValueError(f"Slides file too large. Max {MAX_SLIDES_SIZE_BYTES // (1024 * 1024)} MB.")


def assert_excel_size(num_bytes: int) -> None:
    if num_bytes > MAX_EXCEL_SIZE_BYTES:
        raise ValueError(f"Excel file too large. Max {MAX_EXCEL_SIZE_BYTES // (1024 * 1024)} MB.")
