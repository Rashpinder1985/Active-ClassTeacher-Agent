"""Load agent.md and skills.md from the repository root."""

from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_agent_md() -> str:
    return """# Agent design — Classroom teacher assistant

You are a **teacher** using **local Ollama**. Be clear, fair, and professional.

**Homework:** Sections **Support → Core → Extension**. Per level: **MCQ → fill-in → subjective**; **exact** counts; **Answer key** last (**Support → Core → Extension**). No MCQ answers beside questions.

**Pipeline:** analytics (no LLM) → summary → homework (validated) → badges (top 5).

**Disclaimer:** Analytics = Excel/poll data only; teacher remains in charge.
"""


def default_skills_md() -> str:
    return """# Skills — Teacher agent runbook

**Inputs:** Slides + Excel (id column + questions or marks). Optional Poll/Question/Quiz on slide title for summary. Caps: 50 MB / 10 MB.

**Pipeline:** load_context → analytics (charts, tiers) → summary → homework (validate, retry) → badges (top 5 PDF).

**Analytics:** Custom score bands (0–100 edges) in Streamlit/API. Engagement chart only for poll-style sheets.

**Outputs:** Summary Word; homework Word (Support→Core→Extension; answer key last); badges PDF. Homework uses topic + tier counts, not names.

**Streamlit:** Upload → Analytics → Reports. Sidebar: model, anonymize, validation retries.
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
