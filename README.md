# Classroom Report & Analytics

**Repository:** [github.com/Rashpinder1985/Active-ClassTeacher-Agent](https://github.com/Rashpinder1985/Active-ClassTeacher-Agent)

Local-only tool for teachers: lecture slides (PPT/PDF) + poll responses (Excel) → topic summary (Word), poll analytics (charts), and differentiated homework via **Ollama**. Stack: **LangGraph** + **FastAPI** (primary), **CLI**, optional **Streamlit**. Dependencies: **[uv](https://github.com/astral-sh/uv)** — [`pyproject.toml`](pyproject.toml) / [`uv.lock`](uv.lock) only (no `requirements.txt`).

## Prerequisites

- Python **3.10+** (3.11–3.13 recommended; 3.14 may show LangChain Pydantic warnings)
- **[uv](https://github.com/astral-sh/uv)**
- **[Ollama](https://ollama.com)** — run locally, then e.g. `ollama pull llama3.2`

## Install

```bash
cd "Classroom App"
uv sync
```

Creates `.venv` and installs the `classroom-report` package in editable mode.

## Run

| Interface | Command |
|-----------|---------|
| **API** | `uv run uvicorn app:api_app --reload --host 127.0.0.1 --port 8000` |
| **CLI** | `uv run classroom slides.pptx responses.xlsx --out-dir ./out` — add `--no-summary` / `--no-homework` to skip steps; writes `.docx` and `charts/*.json` |
| **Streamlit** | `uv run streamlit run app.py` — UI is `run_streamlit()` in the same file |

**API:** `GET /health` — status + Ollama. `POST /graph/run` (same as `/run`, `/graph/invoke`) — multipart: `slides`, `responses`; optional form fields `answer_key`, `ollama_model`, `want_summary`, `want_homework`, `anonymize`, `homework_levels_json`, `question_specs_json`. Response: charts (Plotly JSON), `ranked_preview`, `tier_counts`, optional texts, base64 `.docx` when generated.

## Project layout

| Path | Purpose |
|------|---------|
| [`app.py`](app.py) | **Single module:** config, parsers, analytics, pipeline, Ollama client, Word reports, LangGraph agent, FastAPI (`api_app`), CLI (`cli_main`), Streamlit (`run_streamlit`) |
| [`agent.md`](agent.md), [`skills.md`](skills.md) | Agent memory + workflow text (injected into Ollama context); created with defaults if missing |

## File formats

**Slides** — One file per lecture. Slides whose title or first line contains Poll / Question / Quiz are treated as poll context for the summary.

**Excel** — Column **`Student Name`** required.

- **Selected/Correct:** `Q1_Selected`, `Q1_Correct`, … (letters A–D); score 1 when selected matches correct.
- **Wide:** `Q1`, `Q2`, … as `1`/`0` or letters + optional answer key (comma-separated or first row “Key”/“Answer”).

Optional samples under `templates/` (e.g. `poll_responses_example.xlsx`, `lecture_example.pptx`).

## Streamlit flow

Upload files → **Analytics** (top 5, engagement, tiers) → **Reports** (summary + homework `.docx`). Sidebar: Ollama model, anonymize top-5 names.

## Guardrails & limits

- Data stays local; homework prompts use topic + tier counts only (not student names).
- Slides max **50 MB**, Excel max **10 MB**.
- Tiers reflect poll data only — use professional judgment for assignments.

## Troubleshooting

- **Cannot reach Ollama** — Start Ollama and `ollama pull <model>`.
- **Missing `Student Name` column** — Rename column to exactly that text.
- **No slide text** — Use real `.pptx`/`.pdf` with selectable text, not image-only slides.

## Tutorial

Regenerate **Classroom_App_Tutorial.docx**: `uv run python scripts/generate_tutorial_doc.py`

## License

Use and modify as needed for your classroom.
