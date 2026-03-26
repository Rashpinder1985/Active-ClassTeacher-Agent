"""Load agent.md and skills.md from the repository root."""

from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_agent_md() -> str:
    return """# Agent memory — Active class teacher

You support **local-only** classroom analytics. **Lecture slides and the quiz file are independent:** you may upload a **PPT/PDF with no question slides**; put quiz results only in **Excel** (flexible **Name/Email/Roll** + questions or **marks/score**). Full slide text still drives summaries; analytics use **only** the spreadsheet. Optional: slides whose title/first line contains Poll/Question/Quiz add extra summary context. Ollama runs locally.

## Disclaimer

Analytics and tiers are based only on poll responses in Excel; use professional judgment when assigning homework.
"""


def default_skills_md() -> str:
    return """# Skills

## Ingest

1. **Slides** (`.pptx`/`.pdf`): all slide text is extracted. **Poll/Question/Quiz** on a slide title or first line is **optional** extra context for summaries.
2. **Excel** (`.xlsx`): quiz responses **separate from slides** are supported. **Identifier** column (Name, Email, Roll No, …) and **marks/score or Q1/Q2**—detected flexibly. **Wide** (`Q1`…), **Selected/Correct**, or **score-only** (optional **Max Marks**); scores normalized for tiers.

## Analytics

Scores and tiers come **only from Excel**, not from slide content. Charts: score bands (all students), class mean/median/std, top 10; per-question engagement only for poll-style sheets. **LangGraph** steps: analytics (no LLM), summary (Ollama), homework (Ollama + validation pass), badge PDF (Ollama quotes for top five performers).

## Reports

Topic summary uses lecture text + optional poll-slide snippets. Homework uses topic + tier counts only (no student names in LLM); a reviewer checks completeness before the homework report is finalized. MCQ answers in an Answer key section at the end. Top performer badges are **PDF** pages with one quote per student.
"""


def _read_or_create(path: Path, default: str) -> str:
    if path.is_file():
        return path.read_text(encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(default, encoding="utf-8")
    return default


def load_agent_md(root: Path | None = None) -> str:
    return _read_or_create((root or project_root()) / "agent.md", default_agent_md())


def load_skills_md(root: Path | None = None) -> str:
    return _read_or_create((root or project_root()) / "skills.md", default_skills_md())


def combine_agent_skills(agent_context: str, skills_context: str) -> str:
    parts = [p.strip() for p in (agent_context, skills_context) if (p or "").strip()]
    return "\n\n---\n\n".join(parts) if parts else ""
