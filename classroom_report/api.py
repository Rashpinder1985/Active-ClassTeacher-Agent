"""FastAPI routes for the classroom pipeline."""

from __future__ import annotations

import base64
import json
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from classroom_report.graph import invoke_classroom
from classroom_report.ollama import check_ollama_available

api_app = FastAPI(title="Classroom Report Agent", version="0.2.0")


class HealthResponse(BaseModel):
    status: str
    ollama_ok: bool
    ollama_message: str


class RunResponse(BaseModel):
    ingest_ok: bool
    errors: list[str] = Field(default_factory=list)
    tier_counts: dict[str, int] = Field(default_factory=dict)
    ranked_preview: list[dict[str, Any]] = Field(default_factory=list)
    question_columns: list[str] = Field(default_factory=list)
    charts: Optional[dict[str, str]] = None
    analytics_summary: Optional[dict[str, Any]] = None
    summary_text: Optional[str] = None
    homework_text: Optional[str] = None
    summary_docx_base64: Optional[str] = None
    homework_docx_base64: Optional[str] = None
    homework_validation_note: Optional[str] = None
    badge_pdf_base64: Optional[str] = None


@api_app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    ok, msg = check_ollama_available()
    return HealthResponse(status="ok", ollama_ok=ok, ollama_message=msg)


@api_app.post("/graph/run", response_model=RunResponse)
@api_app.post("/run", response_model=RunResponse)
@api_app.post("/graph/invoke", response_model=RunResponse)
async def graph_run(
    slides: UploadFile = File(..., description="Lecture slides .pptx or .pdf"),
    responses: UploadFile = File(..., description="Poll responses .xlsx"),
    answer_key: Optional[str] = Form(None),
    ollama_model: str = Form("llama3.2"),
    want_summary: bool = Form(True),
    want_homework: bool = Form(True),
    anonymize: bool = Form(False),
    homework_levels_json: str = Form('["Extension", "Core", "Support"]'),
    question_specs_json: str = Form(
        '[{"type": "MCQ", "count": 2}, {"type": "Fill in the blanks", "count": 2}, {"type": "Subjective questions", "count": 1}]'
    ),
    score_band_edges_json: str = Form("null"),
    score_band_labels_json: str = Form("null"),
    want_badges: bool = Form(True),
    homework_max_attempts: int = Form(4),
) -> RunResponse:
    try:
        levels = json.loads(homework_levels_json)
        specs = json.loads(question_specs_json)
        raw_edges = json.loads(score_band_edges_json)
        raw_labels = json.loads(score_band_labels_json)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in form fields: {e}") from e

    score_band_edges: list[float] | None = None
    score_band_labels: list[str] | None = None
    if isinstance(raw_edges, list) and len(raw_edges) >= 2:
        try:
            score_band_edges = [float(x) for x in raw_edges]
        except (TypeError, ValueError) as e:
            raise HTTPException(status_code=400, detail="score_band_edges_json must be a JSON array of numbers.") from e
    if isinstance(raw_labels, list) and len(raw_labels) > 0:
        score_band_labels = [str(x) for x in raw_labels]

    s_bytes = await slides.read()
    e_bytes = await responses.read()
    if not s_bytes or not e_bytes:
        raise HTTPException(status_code=400, detail="Slides and responses files must not be empty.")

    state = invoke_classroom(
        slides_bytes=s_bytes,
        excel_bytes=e_bytes,
        slides_filename=slides.filename or "slides.pptx",
        excel_filename=responses.filename or "responses.xlsx",
        answer_key=answer_key,
        ollama_model=ollama_model,
        want_summary=want_summary,
        want_homework=want_homework,
        anonymize=anonymize,
        homework_levels=levels if isinstance(levels, list) else None,
        question_specs=specs if isinstance(specs, list) else None,
        score_band_edges=score_band_edges,
        score_band_labels=score_band_labels,
        want_badges=want_badges,
        homework_max_attempts=max(1, int(homework_max_attempts)),
    )

    sum_b64 = base64.standard_b64encode(state["summary_docx_bytes"]).decode("ascii") if state.get("summary_docx_bytes") else None
    hw_b64 = base64.standard_b64encode(state["homework_docx_bytes"]).decode("ascii") if state.get("homework_docx_bytes") else None
    badge_b64 = base64.standard_b64encode(state["badge_pdf_bytes"]).decode("ascii") if state.get("badge_pdf_bytes") else None

    return RunResponse(
        ingest_ok=bool(state.get("ingest_ok")),
        errors=list(state.get("errors") or []),
        tier_counts=dict(state.get("tier_counts") or {}),
        ranked_preview=list(state.get("ranked_preview") or []),
        question_columns=list(state.get("question_columns") or []),
        charts=state.get("charts"),
        analytics_summary=state.get("analytics_summary"),
        summary_text=state.get("summary_text"),
        homework_text=state.get("homework_text"),
        summary_docx_base64=sum_b64,
        homework_docx_base64=hw_b64,
        homework_validation_note=state.get("homework_validation_note"),
        badge_pdf_base64=badge_b64,
    )
