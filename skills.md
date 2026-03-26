# Skills — What the workflow does (teacher map)

Use this as the **operating checklist** that matches the app: ingest → analyse → report. Each step below lines up with behaviour in `app.py`.

---

## 1. Prepare your files (before you run anything)

### Lecture materials

- One **deck per session** is easiest: **`.pptx`** or **`.pdf`**.
- **Lecture-only decks are OK.** You do **not** need any question or poll text inside the PowerPoint. The app reads **all** slide text for summaries and homework; missing Poll/Question/Quiz slides does **not** block anything.
- **Quiz separate from slides is OK.** Many teachers teach from a clean deck and assess via a **standalone quiz** (worksheet, LMS, clicker export). Upload that assessment in **Excel** as described below; it only needs to align with the **same lesson topic** you are reporting on—not duplicated on a slide.

### Optional: poll snippets on slides (extra context only)

- If you want the **topic summary** to mention **in-slide checks**, mark those slides so the **title or first line** contains **Poll**, **Question**, or **Quiz** (case-insensitive). That text is **optional** extra context for the LLM.
- If you skip this, `poll_questions_text` is empty and the summary still runs on **full lecture text** from the deck.

### Poll / quiz responses (Excel)

- You need a **who** column and **scores or questions**. The app **recognises** common headers: **Name**, **Student Name**, **Email**, **Roll No**, **Student ID**, etc.—you do not need to rename them to `Student Name` in Excel.
- **Format A — Wide:** `Q1`, `Q2`, … with **1 / 0** (or letters) per student. You can supply a **comma-separated answer key** or use a **key row** when the sheet is set up that way.
- **Format B — Selected / Correct:** pairs like `Q1_Selected`, `Q1_Correct` (letters **A–D**), repeated per question—good for clicker-style exports.
- **Format C — Marks/score only (no Q1/Q2):** one column such as **Total Marks**, **Score**, **Percentage**, **Marks obtained**, etc. (or the main numeric column if the header is ambiguous). Optionally add **`Max Marks`** / **Out of** per row; otherwise the **highest mark in the class** scales everyone to a comparable percentage for tiers and charts.

### Size and privacy

- Keep slides under **50 MB** and Excel under **10 MB** (hard limits in the app).
- Prefer running the tool on a **trusted machine**; the design assumes **local Ollama**, not cloud inference for your class data.

---

## 2. Ingest and analytics (what the tool computes)

1. **Parse slides** → **full lecture text** for every slide + **optional** snippets from slides tagged Poll/Question/Quiz (may be **none**).
2. **Parse Excel** → per-question correctness **or** total marks normalized to 0–100% (independent of whether questions appear in the PPT). For per-question sheets, **score %** = correct ÷ attempted (blanks excluded from the denominator fairly).
3. **Assign tiers** by **percentiles** on that score (defaults: **20% / 60% / 20%**). Internal labels are `top` / `average` / `low`; documents and homework use **Extension / Core / Support**.
4. **Charts:** **class score distribution** (all students in bands: under 40%, 40–50%, 50–70%, 70–80%, 80–100%), **summary stats** (mean, median, std, min, max), top **10** scores, and **per-question engagement** only when the Excel is **poll-style** (several questions or binary 0/1 items)—not for marks-only totals. Use these in PLC or parent meetings as **evidence of patterns**, not as a league table of worth.

The **LangGraph** run uses these steps after loading context: **analytics** (scores, tiers, charts—no LLM), **summary** (Ollama topic summary), **homework** (Ollama differentiated tasks + **review**), **badge** (Ollama quotes + PDF for top five performers).

---

## 3. Reports you can generate

### Topic summary (Word)

- Short **1–2 paragraph** factual summary from **slide content**, with **optional** context from poll-tagged slides.
- Use it for: unit records, handouts, or your own planning notes for the next lesson.

### Differentiated homework (Word)

- Sections follow the levels you select (typically **Extension**, **Core**, **Support**).
- Question mix can include **MCQ**, **fill-in-the-blank**, and **short written** items—configured in the UI/CLI/API.
- **Critical:** the LLM is given **topic text** and **counts per tier**, **not student names**—so homework suggestions stay **instructional**, not personally identifying.
- **MCQs:** correct answers must appear in an **Answer key** section at the **end**, not beside each question—mirrors good paper practice and the app’s prompts.

### Homework validation (quality gate)

- After generation, a **reviewer pass** (same local LLM) checks that the homework includes **every requested level** and **enough of each question type per section** as you configured. If it fails, the model **regenerates** the full homework (up to the retry limit you set in Settings).
- The **Word report is only produced** when validation passes or when there is **no topic text** (then validation is skipped and a stub is returned).

### Top performer badges (PDF)

- The **badge** step uses **top five** scores from the Excel analytics, writes **one landscape page per student** (printable like a **flash card**), and asks the model for a **unique motivational quote** per student (fallbacks exist if parsing fails).
- **Anonymize** replaces names with **Student 1…5** on badges as well as charts.

---

## 4. Running the tool (pick your surface)

- **Streamlit:** upload → **Analytics** → **Reports**; sidebar for **model name** and **anonymise** on charts.
- **CLI / API:** same pipeline for scripted or integrated use; health check confirms **Ollama** is reachable.

---

## 5. Guardrails you should internalise

- **Tiers = poll performance snapshot**, not intelligence or character.
- **Homework generation** is a **draft**: align tasks to your **scheme of work**, **accessibility needs**, and **school policy** before distribution.
- If something looks wrong (empty slide text, missing column), **fix the source file** first—garbage in leads to weak summaries and generic homework.

---

## 6. Quick troubleshooting (teacher view)

- **“Cannot reach Ollama”** → start Ollama and ensure a model is pulled (`ollama pull <model>`).
- **No student column detected** → add a clear header (Name, Email, Roll No, …).
- **No text from PDF** → likely a scan-only PDF; use a text-selectable file or re-export.
