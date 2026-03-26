"""LangGraph: load context → analytics → supervisor (LLM routing) → summary / homework / badge → loop."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

import pandas as pd
from langgraph.graph import END, StateGraph

from classroom_report.analytics import (
    assert_excel_size,
    assert_slides_size,
    chart_engagement,
    chart_score_distribution,
    chart_top_performers,
    parse_responses_bytes,
    parse_slides_bytes,
    run_analytics,
)
from classroom_report.badges import build_top_performer_badges_pdf
from classroom_report.config import BADGE_TOP_N, TOP_PERFORMER_CHART_N, normalize_homework_levels
from classroom_report.excel import find_student_name_column
from classroom_report.loaders import combine_agent_skills, load_agent_md, load_skills_md
from classroom_report.ollama import OllamaClient
from classroom_report.reports import build_homework_docx, build_summary_docx


class ClassroomState(TypedDict, total=False):
    agent_context: str
    skills_context: str
    slides_bytes: bytes
    excel_bytes: bytes
    slides_filename: str
    excel_filename: str
    answer_key: str | None
    ollama_model: str
    want_summary: NotRequired[bool]
    want_homework: NotRequired[bool]
    want_badges: NotRequired[bool]
    homework_max_attempts: NotRequired[int]
    anonymize: NotRequired[bool]
    homework_levels: NotRequired[list[str]]
    question_specs: NotRequired[list[dict]]
    score_band_edges: NotRequired[list[float]]
    score_band_labels: NotRequired[list[str]]
    ingest_ok: bool
    lecture_text: str
    poll_questions_text: str
    tier_counts: dict[str, int]
    ranked_preview: list[dict]
    question_columns: list[str]
    charts: dict[str, str]
    analytics_summary: dict[str, Any]
    summary_text: str
    homework_text: str
    homework_validation_note: str
    top_performers_top5: list[dict]
    badge_pdf_bytes: bytes
    summary_docx_bytes: bytes
    homework_docx_bytes: bytes
    errors: list[str]
    router_next: NotRequired[str]
    router_steps: NotRequired[int]
    router_reason: NotRequired[str]


ROUTER_MAX_STEPS = 12
_ROUTER_ORDER = ("summary_agent", "homework_agent", "badge_agent")


def _allowed_post_analytics_nodes(state: ClassroomState) -> list[str]:
    """Which LLM nodes may run next (dependencies enforced in code, not only by the model)."""
    if not state.get("ingest_ok"):
        return []
    want_s = state.get("want_summary", True)
    want_h = state.get("want_homework", True)
    want_b = state.get("want_badges", True)
    lecture = (state.get("lecture_text") or "").strip()
    has_s = bool((state.get("summary_text") or "").strip())
    has_h = bool(state.get("homework_docx_bytes"))
    has_b = bool(state.get("badge_pdf_bytes"))
    top5 = state.get("top_performers_top5") or []
    topic_ok = bool((state.get("summary_text") or state.get("lecture_text") or "").strip())

    allowed: list[str] = []
    if want_s and not has_s and lecture:
        allowed.append("summary_agent")
    if want_h and not has_h and topic_ok:
        if not want_s or has_s:
            allowed.append("homework_agent")
    if want_b and not has_b and len(top5) > 0:
        allowed.append("badge_agent")
    return allowed


def _fallback_router_choice(allowed: list[str]) -> str:
    for k in _ROUTER_ORDER:
        if k in allowed:
            return k
    return allowed[0]


def _validate_router_choice(next_id: str | None, allowed: list[str]) -> str:
    if not allowed:
        return "end"
    if next_id and next_id in allowed:
        return next_id
    return _fallback_router_choice(allowed)


def _router_context_text(state: ClassroomState) -> str:
    tc = state.get("tier_counts") or {}
    summ = state.get("analytics_summary") or {}
    score_stats = summ.get("score_stats") or {}
    return (
        f"want_summary={state.get('want_summary', True)}\n"
        f"want_homework={state.get('want_homework', True)}\n"
        f"want_badges={state.get('want_badges', True)}\n"
        f"tier_counts={tc}\n"
        f"students_n={score_stats.get('n', '?')}\n"
        f"class_mean_pct={score_stats.get('mean', '?')}\n"
        f"has_summary={bool((state.get('summary_text') or '').strip())}\n"
        f"has_homework_doc={bool(state.get('homework_docx_bytes'))}\n"
        f"has_badge_pdf={bool(state.get('badge_pdf_bytes'))}\n"
        f"has_top5={len(state.get('top_performers_top5') or []) > 0}\n"
        f"lecture_has_text={bool((state.get('lecture_text') or '').strip())}\n"
        "Hint: prefer summary_agent before homework_agent when both are still needed."
    )


def _node_supervisor(state: ClassroomState) -> dict[str, Any]:
    errs = list(state.get("errors") or [])
    step = int(state.get("router_steps") or 0) + 1
    if step > ROUTER_MAX_STEPS:
        return {
            "router_next": "end",
            "router_steps": step,
            "router_reason": "Router step cap reached",
            "errors": errs + ["Supervisor: max steps exceeded; stopping."],
        }

    allowed = _allowed_post_analytics_nodes(state)
    if not allowed:
        return {
            "router_next": "end",
            "router_steps": step,
            "router_reason": "No remaining pipeline steps",
        }

    client = OllamaClient(model=state.get("ollama_model") or "llama3.2")
    extra = _extra_system(state)
    ctx = _router_context_text(state)
    try:
        next_id, reason = client.route_next_post_analytics(
            allowed_ids=allowed,
            context_text=ctx,
            extra_system=extra or None,
        )
        next_id = _validate_router_choice(next_id, allowed)
    except Exception as e:
        next_id = _validate_router_choice(None, allowed)
        reason = f"fallback after error: {e}"

    return {"router_next": next_id, "router_steps": step, "router_reason": reason}


def _route_supervisor(state: ClassroomState) -> str:
    n = (state.get("router_next") or "end").strip()
    if n not in ("summary_agent", "homework_agent", "badge_agent", "end"):
        return "end"
    return n


def _node_load_context(state: ClassroomState) -> dict[str, Any]:
    return {"agent_context": load_agent_md(), "skills_context": load_skills_md()}


def _node_analytics_agent(state: ClassroomState) -> dict[str, Any]:
    errs = list(state.get("errors") or [])
    out: dict[str, Any] = {"ingest_ok": False}
    slides_bytes = state.get("slides_bytes") or b""
    excel_bytes = state.get("excel_bytes") or b""
    if not slides_bytes or not excel_bytes:
        return {**out, "errors": errs + ["Both slides_bytes and excel_bytes are required."]}
    slides_name = state.get("slides_filename") or "slides.pptx"
    excel_name = state.get("excel_filename") or "responses.xlsx"
    try:
        assert_slides_size(len(slides_bytes))
        assert_excel_size(len(excel_bytes))
        lecture_text, poll_text = parse_slides_bytes(slides_name, slides_bytes)
        df, q_cols = parse_responses_bytes(excel_bytes, filename=excel_name, answer_key=state.get("answer_key"))
        sbe = state.get("score_band_edges")
        sbl = state.get("score_band_labels")
        bundle = run_analytics(
            df,
            q_cols,
            top_chart_n=TOP_PERFORMER_CHART_N,
            score_band_edges=sbe if isinstance(sbe, list) and len(sbe) > 0 else None,
            score_band_labels=sbl if isinstance(sbl, list) and len(sbl) > 0 else None,
        )
        anonymize = bool(state.get("anonymize", False))
        fig_top = chart_top_performers(bundle.top_performers_df, TOP_PERFORMER_CHART_N, anonymize=anonymize)
        fig_dist = chart_score_distribution(bundle.band_counts)
        charts: dict[str, str] = {
            "top10": fig_top.to_json(),
            "score_distribution": fig_dist.to_json(),
        }
        if bundle.show_engagement:
            charts["engagement"] = chart_engagement(bundle.responses_df, bundle.question_columns).to_json()
        ranked = bundle.ranked_df
        preview_cols = [c for c in ["Student Name", "score_pct", "tier", "rank"] if c in ranked.columns]
        ranked_preview = ranked[preview_cols].head(20).to_dict(orient="records")
        analytics_summary = {
            "score_stats": bundle.score_stats,
            "band_counts": bundle.band_counts,
            "show_engagement": bundle.show_engagement,
            "band_edges": list(bundle.band_edges),
            "band_labels": list(bundle.band_labels),
        }
        tpdf = bundle.top_performers_df.head(BADGE_TOP_N)
        top5_records: list[dict] = []
        if not tpdf.empty:
            nc = find_student_name_column(tpdf)
            for _, row in tpdf.iterrows():
                rk = row["rank"] if "rank" in tpdf.columns else 0
                top5_records.append(
                    {
                        "Student Name": str(row[nc]),
                        "score_pct": float(row["score_pct"]),
                        "rank": int(rk) if pd.notna(rk) else 0,
                    }
                )
        out.update(
            {
                "ingest_ok": True,
                "lecture_text": lecture_text,
                "poll_questions_text": poll_text,
                "tier_counts": bundle.tier_counts,
                "ranked_preview": ranked_preview,
                "top_performers_top5": top5_records,
                "question_columns": bundle.question_columns,
                "charts": charts,
                "analytics_summary": analytics_summary,
            }
        )
        return out
    except Exception as e:
        return {**out, "errors": errs + [str(e)]}


def _route_after_analytics(state: ClassroomState) -> str:
    return "supervisor" if state.get("ingest_ok") else END


def _extra_system(state: ClassroomState) -> str:
    return combine_agent_skills(state.get("agent_context") or "", state.get("skills_context") or "")


def _node_summary_agent(state: ClassroomState) -> dict[str, Any]:
    errs = list(state.get("errors") or [])
    if not state.get("want_summary", True) or not state.get("ingest_ok"):
        return {}
    lecture = (state.get("lecture_text") or "").strip()
    if not lecture:
        return {"errors": errs + ["No text could be extracted from slides for summary."]}
    client = OllamaClient(model=state.get("ollama_model") or "llama3.2")
    extra = _extra_system(state)
    try:
        summary = client.generate_topic_summary(
            lecture, state.get("poll_questions_text") or "", extra_system=extra or None
        )
        return {"summary_text": summary, "summary_docx_bytes": build_summary_docx(summary)}
    except Exception as e:
        return {"errors": errs + [f"Summary generation failed: {e}"]}


def _node_homework_agent(state: ClassroomState) -> dict[str, Any]:
    errs = list(state.get("errors") or [])
    if not state.get("want_homework", True) or not state.get("ingest_ok"):
        return {}
    client = OllamaClient(model=state.get("ollama_model") or "llama3.2")
    topic = (state.get("summary_text") or state.get("lecture_text") or "")[:6000]
    tier_counts = state.get("tier_counts") or {}
    levels = normalize_homework_levels(state.get("homework_levels"))
    specs = state.get("question_specs") or [
        {"type": "MCQ", "count": 2},
        {"type": "Fill in the blanks", "count": 2},
        {"type": "Subjective questions", "count": 1},
    ]
    extra = _extra_system(state)
    try:
        max_att = int(state.get("homework_max_attempts") or 4)
        homework, note = client.generate_homework_until_validated(
            topic,
            tier_counts,
            question_specs=specs,
            levels=levels,
            extra_system=extra or None,
            max_attempts=max_att,
        )
        return {
            "homework_text": homework,
            "homework_docx_bytes": build_homework_docx(homework),
            "homework_validation_note": note,
        }
    except ValueError as e:
        return {"errors": errs + [str(e)]}
    except Exception as e:
        return {"errors": errs + [f"Homework generation failed: {e}"]}


def _node_badge_agent(state: ClassroomState) -> dict[str, Any]:
    errs = list(state.get("errors") or [])
    if not state.get("want_badges", True):
        return {}
    if not state.get("ingest_ok"):
        return {}
    top5 = state.get("top_performers_top5") or []
    if not top5:
        return {}
    anonymize = bool(state.get("anonymize", False))
    client = OllamaClient(model=state.get("ollama_model") or "llama3.2")
    extra = _extra_system(state)
    names: list[str] = []
    scores: list[float] = []
    for i, row in enumerate(top5[:BADGE_TOP_N]):
        name = str(row.get("Student Name") or "")
        if anonymize:
            name = f"Student {i + 1}"
        names.append(name or f"Student {i + 1}")
        try:
            scores.append(float(row.get("score_pct", 0)))
        except (TypeError, ValueError):
            scores.append(0.0)
    try:
        quotes = client.generate_quotes_for_badges(names, scores, extra_system=extra or None)
        entries = list(zip(names, scores, quotes))
        pdf = build_top_performer_badges_pdf(entries)
        return {"badge_pdf_bytes": pdf}
    except Exception as e:
        return {"errors": errs + [f"Badge PDF generation failed: {e}"]}


def build_graph():
    g = StateGraph(ClassroomState)
    g.add_node("load_context", _node_load_context)
    g.add_node("analytics_agent", _node_analytics_agent)
    g.add_node("supervisor", _node_supervisor)
    g.add_node("summary_agent", _node_summary_agent)
    g.add_node("homework_agent", _node_homework_agent)
    g.add_node("badge_agent", _node_badge_agent)
    g.set_entry_point("load_context")
    g.add_edge("load_context", "analytics_agent")
    g.add_conditional_edges(
        "analytics_agent",
        _route_after_analytics,
        {"supervisor": "supervisor", END: END},
    )
    g.add_conditional_edges(
        "supervisor",
        _route_supervisor,
        {
            "summary_agent": "summary_agent",
            "homework_agent": "homework_agent",
            "badge_agent": "badge_agent",
            "end": END,
        },
    )
    g.add_edge("summary_agent", "supervisor")
    g.add_edge("homework_agent", "supervisor")
    g.add_edge("badge_agent", "supervisor")
    return g.compile()


def invoke_classroom(
    *,
    slides_bytes: bytes,
    excel_bytes: bytes,
    slides_filename: str = "slides.pptx",
    excel_filename: str = "responses.xlsx",
    answer_key: str | None = None,
    ollama_model: str = "llama3.2",
    want_summary: bool = True,
    want_homework: bool = True,
    anonymize: bool = False,
    homework_levels: list[str] | None = None,
    question_specs: list[dict] | None = None,
    score_band_edges: list[float] | None = None,
    score_band_labels: list[str] | None = None,
    want_badges: bool = True,
    homework_max_attempts: int = 4,
) -> ClassroomState:
    graph = build_graph()
    init: ClassroomState = {
        "errors": [],
        "slides_bytes": slides_bytes,
        "excel_bytes": excel_bytes,
        "slides_filename": slides_filename,
        "excel_filename": excel_filename,
        "answer_key": answer_key,
        "ollama_model": ollama_model,
        "want_summary": want_summary,
        "want_homework": want_homework,
        "anonymize": anonymize,
        "homework_levels": normalize_homework_levels(homework_levels),
        "question_specs": question_specs
        or [
            {"type": "MCQ", "count": 2},
            {"type": "Fill in the blanks", "count": 2},
            {"type": "Subjective questions", "count": 1},
        ],
        "want_badges": want_badges,
        "homework_max_attempts": max(1, int(homework_max_attempts)),
        "router_steps": 0,
    }
    if score_band_edges is not None:
        init["score_band_edges"] = score_band_edges
    if score_band_labels is not None:
        init["score_band_labels"] = score_band_labels
    return graph.invoke(init)  # type: ignore[return-value]
