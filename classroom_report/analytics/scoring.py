"""Deterministic scoring and tier assignment from poll response DataFrame."""
from typing import List, Optional, Tuple

import pandas as pd

from classroom_report.config import TIER_AVERAGE_PCT, TIER_LOW_PCT, TIER_TOP_PCT
from classroom_report.parsers.responses import _find_student_name_column, _get_question_columns


def compute_scores(
    df: pd.DataFrame,
    question_columns: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Compute per-student score = (number correct) / (number answered).
    Blank/missing excluded from denominator. Returns df with 'score' and 'answered' columns.
    """
    name_col = _find_student_name_column(df)
    if question_columns is None:
        question_columns = _get_question_columns(df, name_col)
    q = df[question_columns]
    # Coerce to numeric 0/1 in case Excel left strings (e.g. "1.0")
    q = q.apply(pd.to_numeric, errors="coerce").fillna(0).clip(0, 1)
    answered = q.notna() & (q != "")
    correct = (q == 1).fillna(False)
    n_answered = answered.sum(axis=1).astype(int)
    n_correct = (correct & answered).sum(axis=1).astype(int)
    score = n_correct / n_answered.replace(0, float("nan"))
    out = df[[name_col]].copy()
    out["answered"] = n_answered
    out["score"] = score
    out["score_pct"] = (score * 100).round(1)
    return out


def assign_tiers(
    scores_df: pd.DataFrame,
    top_pct: int = TIER_TOP_PCT,
    average_pct: int = TIER_AVERAGE_PCT,
    low_pct: int = TIER_LOW_PCT,
) -> pd.DataFrame:
    """
    Assign tier by percentile: top_pct = 'top', next average_pct = 'average', rest = 'low'.
    scores_df must have 'score' column. Adds 'tier' and 'rank' columns.
    """
    df = scores_df.copy()
    df = df.dropna(subset=["score"])
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    n = len(df)
    df["rank"] = range(1, n + 1)
    if n == 0:
        df["tier"] = []
        return df
    top_n = max(1, round(n * top_pct / 100))
    low_n = max(0, round(n * low_pct / 100))
    mid_n = n - top_n - low_n
    tier = ["top"] * top_n + ["average"] * mid_n + ["low"] * low_n
    df["tier"] = tier[:n]
    return df


def get_top_n(ranked_df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Return top N performers (by rank)."""
    name_col = _find_student_name_column(ranked_df)
    if "rank" not in ranked_df.columns:
        return ranked_df.head(n)
    return ranked_df.nsmallest(n, "rank")[[name_col, "score", "score_pct", "rank"]]
