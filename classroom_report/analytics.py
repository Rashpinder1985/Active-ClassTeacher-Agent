"""Scoring, tiers, charts, and slide/Excel pipeline helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, List, Optional, Sequence, Tuple

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from classroom_report.config import (
    MAX_EXCEL_SIZE_BYTES,
    MAX_SLIDES_SIZE_BYTES,
    STUDENT_NAME_COLUMN,
    TIER_AVERAGE_PCT,
    TIER_LOW_PCT,
    TIER_TOP_PCT,
    TOP_PERFORMER_CHART_N,
)
from classroom_report.excel import find_student_name_column, get_question_columns, load_responses, normalize_responses
from classroom_report.slides import extract_text_from_pdf, extract_text_from_pptx, get_poll_slides


# Score % bands for whole-class distribution (all students) — defaults
DEFAULT_SCORE_BAND_LABELS = ("< 40%", "40–50%", "50–70%", "70–80%", "80–100%")
DEFAULT_SCORE_BAND_EDGES = (0, 40, 50, 70, 80, 100.001)
SCORE_BAND_LABELS = DEFAULT_SCORE_BAND_LABELS
SCORE_BAND_EDGES = DEFAULT_SCORE_BAND_EDGES


def parse_score_band_edges_string(s: str) -> list[float]:
    """Parse comma- or semicolon-separated score band edges (percent, 0–100)."""
    if not (s or "").strip():
        raise ValueError("Score band edges cannot be empty.")
    parts = [p.strip() for p in s.replace(";", ",").split(",") if p.strip()]
    if len(parts) < 2:
        raise ValueError("Provide at least two edges (e.g. 0, 40, 100).")
    try:
        return [float(p) for p in parts]
    except ValueError as e:
        raise ValueError("Score band edges must be numbers separated by commas.") from e


def parse_optional_band_labels_string(s: str) -> list[str]:
    """Comma-separated labels; one label per band (len = number of edges − 1)."""
    if not (s or "").strip():
        return []
    return [p.strip() for p in s.replace(";", ",").split(",") if p.strip()]


def _default_band_labels_from_edges(edges: Sequence[float]) -> Tuple[str, ...]:
    n = len(edges) - 1
    if n < 1:
        return ()
    out: list[str] = []
    for i in range(n):
        lo = float(edges[i])
        hi_raw = float(edges[i + 1])
        hi = min(hi_raw, 100.0)
        if i == 0 and lo == 0:
            out.append(f"< {hi:.0f}%")
        elif i == n - 1 and hi_raw >= 100:
            out.append(f"{lo:.0f}–100%")
        else:
            out.append(f"{lo:.0f}–{hi:.0f}%")
    return tuple(out)


def normalize_score_bands(
    edges: Sequence[float] | None,
    labels: Sequence[str] | None = None,
) -> tuple[tuple[float, ...], tuple[str, ...]]:
    """
    Validate user edges (0 … 100, strictly increasing, covering full range) and build
    pd.cut bins (last edge 100 → 100.001 so 100% is included).

    If edges already end above 100 (e.g. 100.001 from a prior run), treat them as
    finalized bin breakpoints and require one label per band.
    """
    if edges is None or len(edges) == 0:
        return DEFAULT_SCORE_BAND_EDGES, DEFAULT_SCORE_BAND_LABELS
    e = [float(x) for x in edges]
    if len(e) < 2:
        raise ValueError("At least two band edges are required (e.g. 0 and 100).")
    if e != sorted(e):
        raise ValueError("Score band edges must be in ascending order.")
    if len(set(e)) != len(e):
        raise ValueError("Score band edges must be strictly increasing (no duplicates).")
    n_bands = len(e) - 1
    if e[-1] > 100:
        if e[0] != 0:
            raise ValueError("First edge must be 0%.")
        if labels is None or len(list(labels)) != n_bands:
            raise ValueError(
                f"Provide exactly {n_bands} band labels matching the bin edges."
            )
        lab = tuple(str(x).strip() for x in labels)
        return tuple(e), lab
    if e[0] != 0:
        raise ValueError("First edge must be 0%.")
    if e[-1] != 100:
        raise ValueError("Last edge must be 100% so all scores are binned.")
    bins = list(e[:-1]) + [100.001]
    if labels is not None and len(list(labels)) > 0:
        lab = [str(x).strip() for x in labels if str(x).strip()]
        if len(lab) != n_bands:
            raise ValueError(
                f"Number of labels ({len(lab)}) must match number of bands ({n_bands}). "
                f"Provide {n_bands} labels or leave labels empty for auto labels."
            )
        return tuple(bins), tuple(lab)
    return tuple(bins), _default_band_labels_from_edges(e)


@dataclass
class AnalyticsBundle:
    responses_df: pd.DataFrame
    question_columns: list[str]
    scores_df: pd.DataFrame
    ranked_df: pd.DataFrame
    top_performers_df: pd.DataFrame
    tier_counts: dict[str, int]
    show_engagement: bool = False
    score_stats: dict[str, Any] = field(default_factory=dict)
    band_counts: dict[str, int] = field(default_factory=dict)
    band_edges: Tuple[float, ...] = DEFAULT_SCORE_BAND_EDGES
    band_labels: Tuple[str, ...] = DEFAULT_SCORE_BAND_LABELS


def compute_scores(df: pd.DataFrame, question_columns: Optional[List[str]] = None) -> pd.DataFrame:
    name_col = find_student_name_column(df)
    if question_columns is None:
        question_columns = get_question_columns(df, name_col)
    q = df[question_columns].apply(pd.to_numeric, errors="coerce")
    answered = q.notna() & (q != "")
    denom = answered.sum(axis=1).astype(float)
    numer = q.where(answered).sum(axis=1, min_count=0)
    score = numer / denom.replace(0, float("nan"))
    out = df[[name_col]].copy()
    out["answered"] = denom.fillna(0).astype(int)
    out["score"] = score
    out["score_pct"] = (score * 100).round(1)
    return out


def assign_tiers(
    scores_df: pd.DataFrame,
    top_pct: int = TIER_TOP_PCT,
    average_pct: int = TIER_AVERAGE_PCT,
    low_pct: int = TIER_LOW_PCT,
) -> pd.DataFrame:
    df = scores_df.copy().dropna(subset=["score"])
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
    name_col = find_student_name_column(ranked_df)
    if "rank" not in ranked_df.columns:
        return ranked_df.head(n)
    return ranked_df.nsmallest(n, "rank")[[name_col, "score", "score_pct", "rank"]]


def _series_is_binary_poll(s: pd.Series) -> bool:
    v = pd.to_numeric(s, errors="coerce").dropna()
    if v.empty:
        return True
    return bool(((v == 0) | (v == 1)).all())


def is_poll_based_sheet(df: pd.DataFrame, question_columns: list[str]) -> bool:
    """
    Engagement-by-question chart only for per-question (poll) sheets:
    multiple questions, or a single column of binary 0/1 responses.
    Total-marks-only sheets (one synthetic fractional Q1) are excluded.
    """
    if len(question_columns) >= 2:
        return True
    if len(question_columns) == 0:
        return False
    s = pd.to_numeric(df[question_columns[0]], errors="coerce").dropna()
    if s.empty:
        return False
    return bool(((s == 0) | (s == 1)).all())


def class_score_statistics(score_pct: pd.Series) -> dict[str, Any]:
    s = pd.to_numeric(score_pct, errors="coerce").dropna()
    if s.empty:
        return {"n": 0, "mean": 0.0, "median": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
    return {
        "n": int(len(s)),
        "mean": round(float(s.mean()), 2),
        "median": round(float(s.median()), 2),
        "std": round(float(s.std()), 2) if len(s) > 1 else 0.0,
        "min": round(float(s.min()), 2),
        "max": round(float(s.max()), 2),
    }


def score_band_counts(
    score_pct: pd.Series,
    band_edges: Sequence[float] | None = None,
    band_labels: Sequence[str] | None = None,
) -> dict[str, int]:
    edges_t, labels_t = normalize_score_bands(
        list(band_edges) if band_edges is not None else None,
        list(band_labels) if band_labels is not None else None,
    )
    s = pd.to_numeric(score_pct, errors="coerce").dropna()
    if s.empty:
        return {lab: 0 for lab in labels_t}
    s = s.clip(0, 100)
    cats = pd.cut(
        s,
        bins=list(edges_t),
        labels=list(labels_t),
        right=False,
        include_lowest=True,
    )
    vc = cats.value_counts()
    return {lab: int(vc.get(lab, 0)) for lab in labels_t}


def chart_score_distribution(band_counts: dict[str, int]) -> go.Figure:
    labels = list(band_counts.keys())
    counts = [band_counts.get(lab, 0) for lab in labels]
    fig = go.Figure(
        data=[
            go.Bar(
                x=labels,
                y=counts,
                text=counts,
                textposition="outside",
                marker_color="#636EFA",
            )
        ]
    )
    fig.update_layout(
        title="Class score distribution (all students)",
        xaxis_title="Score range (%)",
        yaxis_title="Number of students",
        showlegend=False,
    )
    return fig


def chart_top_performers(
    top_df: pd.DataFrame,
    n: int,
    anonymize: bool = False,
    name_col: Optional[str] = None,
) -> go.Figure:
    if top_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig
    name_col = name_col or STUDENT_NAME_COLUMN
    df = top_df.copy()
    df["Display"] = [f"Student {i+1}" for i in range(len(df))] if anonymize else df[name_col].astype(str)
    fig = px.bar(
        df,
        x="Display",
        y="score_pct",
        title=f"Top {n} scores (%)",
        labels={"score_pct": "Score (%)", "Display": "Student"},
        text_auto=".1f",
    )
    fig.update_layout(xaxis_tickangle=-45, showlegend=False)
    return fig


def chart_engagement(responses_df: pd.DataFrame, question_columns: List[str]) -> go.Figure:
    q = responses_df[question_columns].apply(pd.to_numeric, errors="coerce")
    answered = q.notna() & (q != "")
    count_answered = answered.sum().astype(int)
    pct_second: List[float] = []
    for col in question_columns:
        s = q[col]
        ans = answered[col]
        if _series_is_binary_poll(s):
            denom = int(ans.sum())
            pct = float(((s == 1) & ans).sum() / denom * 100) if denom else 0.0
        else:
            denom = int(ans.sum())
            pct = float(s[ans].mean() * 100) if denom else 0.0
        pct_second.append(round(pct, 1))
    metric_label = "Correct %" if all(_series_is_binary_poll(q[c]) for c in question_columns) else "Avg score %"
    plot_df = pd.DataFrame({"Question": question_columns, "Answered": count_answered.values, metric_label: pct_second})
    fig = go.Figure()
    fig.add_trace(
        go.Bar(name="Responses", x=plot_df["Question"], y=plot_df["Answered"], text=plot_df["Answered"].astype(int), textposition="outside")
    )
    fig.add_trace(go.Scatter(x=plot_df["Question"], y=plot_df[metric_label], name=metric_label, mode="lines+markers", yaxis="y2"))
    fig.update_layout(
        title="Poll engagement by question",
        xaxis_title="Question",
        yaxis=dict(title="Number of responses"),
        yaxis2=dict(title=metric_label, overlaying="y", side="right", range=[0, 105]),
        barmode="group",
        showlegend=True,
    )
    return fig


def parse_slides_bytes(filename: str, data: bytes) -> tuple[str, str]:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    buf = BytesIO(data)
    buf.name = filename
    if ext == "pptx":
        full_text, slides_text = extract_text_from_pptx(buf)
    elif ext == "pdf":
        full_text, slides_text = extract_text_from_pdf(buf)
    else:
        return "", ""
    poll_slides = get_poll_slides(slides_text)
    poll_text = "\n\n".join(f"Slide {i}: {t}" for i, t in poll_slides) if poll_slides else ""
    return full_text, poll_text


def parse_responses_bytes(
    excel_bytes: bytes,
    filename: str = "responses.xlsx",
    answer_key: Optional[str] = None,
) -> tuple[pd.DataFrame, list[str]]:
    buf = BytesIO(excel_bytes)
    buf.name = filename
    df = load_responses(buf, answer_key=answer_key)
    return normalize_responses(df)


def run_analytics(
    df: pd.DataFrame,
    question_columns: list[str],
    top_chart_n: int = TOP_PERFORMER_CHART_N,
    score_band_edges: Sequence[float] | None = None,
    score_band_labels: Sequence[str] | None = None,
) -> AnalyticsBundle:
    edges_t, labels_t = normalize_score_bands(
        list(score_band_edges) if score_band_edges is not None else None,
        list(score_band_labels) if score_band_labels is not None else None,
    )
    scores_df = compute_scores(df, question_columns)
    ranked_df = assign_tiers(scores_df)
    top_performers_df = get_top_n(ranked_df, top_chart_n)
    tier_counts = ranked_df["tier"].value_counts().to_dict() if "tier" in ranked_df.columns else {}
    show_engagement = is_poll_based_sheet(df, question_columns)
    sp = ranked_df["score_pct"] if "score_pct" in ranked_df.columns else scores_df["score_pct"]
    score_stats = class_score_statistics(sp)
    band_counts = score_band_counts(sp, band_edges=edges_t, band_labels=labels_t)
    return AnalyticsBundle(
        responses_df=df,
        question_columns=question_columns,
        scores_df=scores_df,
        ranked_df=ranked_df,
        top_performers_df=top_performers_df,
        tier_counts=tier_counts,
        show_engagement=show_engagement,
        score_stats=score_stats,
        band_counts=band_counts,
        band_edges=edges_t,
        band_labels=labels_t,
    )


def assert_slides_size(num_bytes: int) -> None:
    if num_bytes > MAX_SLIDES_SIZE_BYTES:
        raise ValueError(f"Slides file too large. Max {MAX_SLIDES_SIZE_BYTES // (1024 * 1024)} MB.")


def assert_excel_size(num_bytes: int) -> None:
    if num_bytes > MAX_EXCEL_SIZE_BYTES:
        raise ValueError(f"Excel file too large. Max {MAX_EXCEL_SIZE_BYTES // (1024 * 1024)} MB.")
