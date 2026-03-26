"""Load agent.md (memory/persona) and skills.md (workflow instructions)."""
from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """Repository root (parent of the ``classroom_report`` package)."""
    return Path(__file__).resolve().parents[2]


def default_agent_md() -> str:
    return """# Agent memory

You support teachers with **local-only** classroom analytics and report generation.

## Principles

- Prefer concise, factual outputs suitable for class reports.
- Respect file formats: slides as PPT/PDF, poll data as Excel with `Student Name`.
- Do not send data to the cloud; Ollama runs locally.

## Disclaimer

Analytics and tiers are based only on poll responses; use professional judgment when assigning homework.
"""


def default_skills_md() -> str:
    return """# Skills

## Ingest

1. Accept lecture slides (`.pptx` or `.pdf`) and poll responses (`.xlsx`).
2. Parse slides for full text and poll-tagged slides (titles containing Poll/Question/Quiz).
3. Parse Excel: wide format (`Q1`, `Q2`, …) or Selected/Correct pairs (`Q1_Selected`, `Q1_Correct`).

## Analytics

1. Score students, assign tiers (Extension / Core / Support), compute top performers.
2. Build engagement charts from question columns.

## Reports

1. **Topic summary** — short class summary from slide content (optional poll context).
2. **Homework** — differentiated Extension / Core / Support; no student names in LLM prompts for homework (only topic + tier counts).

## Guardrails

- Homework prompts: include topic text and tier counts only — not student names.
- MCQ answers belong in a final Answer key section, not inline.
"""


def _read_or_create(path: Path, default: str) -> str:
    if path.is_file():
        return path.read_text(encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(default, encoding="utf-8")
    return default


def load_agent_md(root: Path | None = None) -> str:
    p = (root or project_root()) / "agent.md"
    return _read_or_create(p, default_agent_md())


def load_skills_md(root: Path | None = None) -> str:
    p = (root or project_root()) / "skills.md"
    return _read_or_create(p, default_skills_md())


def combine_agent_skills(agent_context: str, skills_context: str) -> str:
    parts: list[str] = []
    if (agent_context or "").strip():
        parts.append(agent_context.strip())
    if (skills_context or "").strip():
        parts.append(skills_context.strip())
    return "\n\n---\n\n".join(parts) if parts else ""
