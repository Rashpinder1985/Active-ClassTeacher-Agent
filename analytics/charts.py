"""Plotly charts for top 5 performers and per-question engagement."""
from typing import List, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from config import STUDENT_NAME_COLUMN


def chart_top5(
    top5_df: pd.DataFrame,
    anonymize: bool = False,
    name_col: Optional[str] = None,
) -> go.Figure:
    """Bar chart of top 5 performers: name (or Student 1..5) vs score %."""
    if top5_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig
    name_col = name_col or STUDENT_NAME_COLUMN
    df = top5_df.copy()
    if anonymize:
        df["Display"] = [f"Student {i+1}" for i in range(len(df))]
    else:
        df["Display"] = df[name_col].astype(str)
    fig = px.bar(
        df,
        x="Display",
        y="score_pct",
        title="Top 5 performers (poll score %)",
        labels={"score_pct": "Score (%)", "Display": "Student"},
        text_auto=".1f",
    )
    fig.update_layout(xaxis_tickangle=-45, showlegend=False)
    return fig


def chart_engagement(
    responses_df: pd.DataFrame,
    question_columns: List[str],
) -> go.Figure:
    """Bar chart: per-question engagement (count answered) and optionally % correct."""
    q = responses_df[question_columns].apply(pd.to_numeric, errors="coerce").fillna(0)
    answered = q.notna() & (q != "")
    count_answered = answered.sum().astype(int)
    correct = (q == 1) & answered
    pct_correct = correct.sum() / count_answered.replace(0, float("nan")) * 100
    df = pd.DataFrame({
        "Question": question_columns,
        "Answered": count_answered.values,
        "Correct %": pct_correct.values.round(1),
    })
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Responses", x=df["Question"], y=df["Answered"], text=df["Answered"].astype(int), textposition="outside"))
    fig.add_trace(go.Scatter(x=df["Question"], y=df["Correct %"], name="Correct %", mode="lines+markers", yaxis="y2"))
    fig.update_layout(
        title="Poll engagement by question",
        xaxis_title="Question",
        yaxis=dict(title="Number of responses"),
        yaxis2=dict(title="Correct %", overlaying="y", side="right", range=[0, 105]),
        barmode="group",
        showlegend=True,
    )
    return fig
