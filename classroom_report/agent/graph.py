"""LangGraph workflow: load context → ingest → optional summary → optional homework."""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from .loaders import combine_agent_skills, load_agent_md, load_skills_md
from .state import ClassroomState
from classroom_report.llm.ollama_client import OllamaClient
from classroom_report.pipeline.ingest import (
    assert_excel_size,
    assert_slides_size,
    parse_responses_bytes,
    parse_slides_bytes,
    run_analytics,
)
from classroom_report.reports.homework_doc import build_homework_docx
from classroom_report.reports.summary_doc import build_summary_docx


def _node_load_context(state: ClassroomState) -> dict[str, Any]:
    agent = load_agent_md()
    skills = load_skills_md()
    return {"agent_context": agent, "skills_context": skills}


def _node_ingest(state: ClassroomState) -> dict[str, Any]:
    errs = list(state.get("errors") or [])
    out: dict[str, Any] = {"ingest_ok": False}
    slides_bytes = state.get("slides_bytes") or b""
    excel_bytes = state.get("excel_bytes") or b""
    if not slides_bytes or not excel_bytes:
        return {**out, "errors": errs + ["Both slides_bytes and excel_bytes are required."]}
    slides_name = state.get("slides_filename") or "slides.pptx"
    excel_name = state.get("excel_filename") or "responses.xlsx"
    try:
        from classroom_report.analytics.charts import chart_engagement, chart_top5

        assert_slides_size(len(slides_bytes))
        assert_excel_size(len(excel_bytes))
        lecture_text, poll_text = parse_slides_bytes(slides_name, slides_bytes)
        df, q_cols = parse_responses_bytes(
            excel_bytes,
            filename=excel_name,
            answer_key=state.get("answer_key"),
        )
        bundle = run_analytics(df, q_cols)
        anonymize = bool(state.get("anonymize", False))
        fig_top = chart_top5(bundle.top5_df, anonymize=anonymize)
        fig_eng = chart_engagement(bundle.responses_df, bundle.question_columns)
        ranked = bundle.ranked_df
        preview_cols = [c for c in ["Student Name", "score_pct", "tier", "rank"] if c in ranked.columns]
        ranked_preview = ranked[preview_cols].head(20).to_dict(orient="records")
        out.update(
            {
                "ingest_ok": True,
                "lecture_text": lecture_text,
                "poll_questions_text": poll_text,
                "tier_counts": bundle.tier_counts,
                "ranked_preview": ranked_preview,
                "question_columns": bundle.question_columns,
                "charts": {
                    "top5": fig_top.to_json(),
                    "engagement": fig_eng.to_json(),
                },
            }
        )
        return out
    except Exception as e:
        return {**out, "errors": errs + [str(e)]}


def _route_after_ingest(state: ClassroomState) -> str:
    if state.get("ingest_ok"):
        return "llm_summary"
    return END


def _extra_system(state: ClassroomState) -> str:
    return combine_agent_skills(
        state.get("agent_context") or "",
        state.get("skills_context") or "",
    )


def _node_summary(state: ClassroomState) -> dict[str, Any]:
    errs = list(state.get("errors") or [])
    if not state.get("want_summary", True):
        return {}
    if not state.get("ingest_ok"):
        return {}
    lecture = (state.get("lecture_text") or "").strip()
    if not lecture:
        return {"errors": errs + ["No text could be extracted from slides for summary."]}
    model = state.get("ollama_model") or "llama3.2"
    client = OllamaClient(model=model)
    extra = _extra_system(state)
    try:
        summary = client.generate_topic_summary(
            lecture,
            state.get("poll_questions_text") or "",
            extra_system=extra or None,
        )
        doc_bytes = build_summary_docx(summary)
        return {"summary_text": summary, "summary_docx_bytes": doc_bytes}
    except Exception as e:
        return {"errors": errs + [f"Summary generation failed: {e}"]}


def _node_homework(state: ClassroomState) -> dict[str, Any]:
    errs = list(state.get("errors") or [])
    if not state.get("want_homework", True):
        return {}
    if not state.get("ingest_ok"):
        return {}
    model = state.get("ollama_model") or "llama3.2"
    client = OllamaClient(model=model)
    topic = (state.get("summary_text") or state.get("lecture_text") or "")[:6000]
    tier_counts = state.get("tier_counts") or {}
    levels = state.get("homework_levels") or ["Extension", "Core", "Support"]
    specs = state.get("question_specs") or [
        {"type": "MCQ", "count": 3},
        {"type": "Fill in the blanks", "count": 2},
        {"type": "Subjective questions", "count": 1},
    ]
    extra = _extra_system(state)
    try:
        homework = client.generate_differentiated_homework(
            topic,
            tier_counts,
            question_specs=specs,
            levels=levels,
            extra_system=extra or None,
        )
        doc_bytes = build_homework_docx(homework)
        return {"homework_text": homework, "homework_docx_bytes": doc_bytes}
    except Exception as e:
        return {"errors": errs + [f"Homework generation failed: {e}"]}


def build_graph():
    g = StateGraph(ClassroomState)
    g.add_node("load_context", _node_load_context)
    g.add_node("ingest", _node_ingest)
    g.add_node("llm_summary", _node_summary)
    g.add_node("llm_homework", _node_homework)

    g.set_entry_point("load_context")
    g.add_edge("load_context", "ingest")
    g.add_conditional_edges("ingest", _route_after_ingest, {"llm_summary": "llm_summary", END: END})
    g.add_edge("llm_summary", "llm_homework")
    g.add_edge("llm_homework", END)

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
) -> ClassroomState:
    """Run the compiled graph and return final state."""
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
        "homework_levels": homework_levels or ["Extension", "Core", "Support"],
        "question_specs": question_specs
        or [
            {"type": "MCQ", "count": 3},
            {"type": "Fill in the blanks", "count": 2},
            {"type": "Subjective questions", "count": 1},
        ],
    }
    result = graph.invoke(init)
    return result  # type: ignore[return-value]
