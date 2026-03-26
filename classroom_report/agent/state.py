"""LangGraph state: dynamic optional fields via total=False."""
from __future__ import annotations

from typing import NotRequired, TypedDict


class ClassroomState(TypedDict, total=False):
    """Workflow state; fields appear as the run progresses."""

    # Loaded from agent.md / skills.md
    agent_context: str
    skills_context: str

    # Inputs
    slides_bytes: bytes
    excel_bytes: bytes
    slides_filename: str
    excel_filename: str
    answer_key: str | None
    ollama_model: str
    want_summary: NotRequired[bool]
    want_homework: NotRequired[bool]
    anonymize: NotRequired[bool]
    homework_levels: NotRequired[list[str]]
    question_specs: NotRequired[list[dict]]

    # Ingest + analytics
    ingest_ok: bool
    lecture_text: str
    poll_questions_text: str
    tier_counts: dict[str, int]
    ranked_preview: list[dict]
    question_columns: list[str]
    charts: dict[str, str]

    # LLM outputs
    summary_text: str
    homework_text: str
    summary_docx_bytes: bytes
    homework_docx_bytes: bytes

    errors: list[str]
