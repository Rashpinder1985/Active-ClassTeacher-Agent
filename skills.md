# Skills — Teacher agent runbook

*Operational spec for the classroom app. Aligned with `classroom_report/` (graph, API, Streamlit). Use this as the single source for “what the product does.”*

---

## Inputs

| Input | Rule |
|-------|------|
| **Slides** `.pptx` / `.pdf` | All slide text is read. Lecture-only decks are fine (no questions on slides required). |
| **Excel** | One **student id** column (Name, Email, Roll, …—auto-detected) + **questions** (`Q1`… or Selected/Correct) **or** **marks/score** (+ optional Max Marks). |
| **Poll on slides (optional)** | Put **Poll**, **Question**, or **Quiz** in the **slide title or first line** → extra text for the **summary** only. |

**Size caps:** slides **50 MB**, Excel **10 MB**.

---

## Pipeline (order)

```
load_context → analytics_agent → supervisor ⟷ summary_agent | homework_agent | badge_agent → END
                      ↑ no LLM        ↑ LLM routes          ↑ each node returns to supervisor
```

- **analytics_agent:** Scores, tiers, charts, top **10**, optional engagement, top **5** for badges. **No LLM.** Uses optional **`score_band_edges` / `score_band_labels`** from invoke when provided.
- **supervisor:** After analytics, a **local LLM** picks the **next** step from an **allowed** list (code enforces dependencies: e.g. summary before homework when both are on). Steps repeat until nothing is left or a **step cap** is hit. Exposes **`router_steps`**, **`router_reason`** on the returned state.
- **summary_agent / homework_agent / badge_agent:** Same behaviour as before; **homework** still runs the **reviewer** loop before Word. Respects **`want_summary` / `want_homework` / `want_badges`**.

---

## Analytics (teacher-facing)

- **Tiers:** Default split **20% / 60% / 20%** → labels **Extension / Core / Support**.
- **Charts:** Score distribution (histogram), summary stats, top 10, engagement chart only for **poll-style** sheets.
- **Custom bins:** In **Streamlit → Analytics** or **Reports** (full pipeline section), set band **edges** (comma-separated, **0 … 100**). Optional **labels**. Same keys feed **`invoke_classroom`** as **`score_band_edges` / `score_band_labels`** (API/CLI JSON arrays).

---

## Outputs

| Output | What it is |
|--------|------------|
| **Topic summary** | Word; from slide text ± optional poll snippets. |
| **Homework** | Word; levels **Support → Core → Extension**; per level: MCQ → fill-in → subjective; **exact** counts from UI/API; **Answer key** last (**Support → Core → Extension**). |
| **Badges** | PDF, top **5** scores; one quote per student; **Anonymize** → “Student 1…” on charts and badges. |

**Homework privacy:** Prompts use **topic + tier counts**, not student names.

---

## Where to click (Streamlit)

1. **Upload** — slides + Excel.  
2. **Analytics** — metrics, charts, optional **custom score bands**.  
3. **Reports** — **Run full report pipeline** (`invoke_classroom`): human-in-the-loop **bands**, **`want_*` toggles**, **homework levels** and **question counts**, then downloads plus optional **Supervisor (router)** log (`router_steps`, `router_reason`, errors). Or generate **summary**, **homework**, and **badges** step-by-step with the same homework controls.

**Sidebar:** Ollama model, anonymize, **homework validation retries**.

**CLI / API:** Same graph via **`invoke_classroom`**; knobs include **`want_summary` / `want_homework` / `want_badges`**, score bands, `homework_max_attempts`, `homework_levels` / `question_specs` (normalized levels **Support → Core → Extension**).

---

## If something breaks

| Symptom | Fix |
|---------|-----|
| Ollama errors | Start Ollama; `ollama pull <model>`. |
| No student column | Add a clear header (Name, Email, Roll …). |
| Empty slide text | PDF may be image-only; use text you can select. |

---

## Guardrails

- Homework output is a **draft**—teacher aligns with curriculum and policy.  
- **Tiers** = snapshot from the sheet, not fixed ability labels.
