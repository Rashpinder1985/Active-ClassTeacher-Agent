# Classroom Report & Analytics

A **local-only** web app for teachers: upload lecture slides (PPT or PDF) and poll responses (Excel), then generate a topic summary report, visual poll analytics (engagement + top 5 performers), and differentiated homework (Word) using a local LLM (Ollama). All data stays on your machine.

## Prerequisites

- **Python 3.9+**
- **Ollama** ([ollama.com](https://ollama.com)) — install and run locally, then pull a model:
  ```bash
  ollama pull llama3.2
  ```

## Installation

1. Open a terminal and go to the app folder:
   ```bash
   cd "Classroom App"
   ```
2. Create a virtual environment (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate   # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the app:
   ```bash
   streamlit run app.py
   ```
5. Open the URL shown (usually http://localhost:8501) in your browser.

## File formats

### Lecture slides (PPT or PDF)

- One file per lecture.
- Poll questions can be on slides whose **title or first line** contains "Poll", "Question", or "Quiz" — the app uses these to improve context for the summary.

### Poll responses (Excel)

Two formats are supported:

**Format 1 — Selected/Correct (e.g. from polling tools)**  
- **Required column:** `Student Name`.
- For each question, two columns: `Qn_Selected` (answer chosen: A/B/C/D) and `Qn_Correct` (correct answer for that question).  
  Example: `Q1_Selected`, `Q1_Correct`, `Q2_Selected`, `Q2_Correct`, …
- The app scores 1 where Selected equals Correct, 0 otherwise.

**Format 2 — Wide (single column per question)**  
- **Required column:** `Student Name`.
- **Question columns:** e.g. `Q1`, `Q2`, … with `1` = correct, `0` = incorrect, or letters A/B/C and an **answer key** (comma-separated, e.g. `A,B,A,C`).
- **Optional:** first row can be the answer key if the first cell in the name column is "Key" or "Answer".

See `templates/poll_responses_example.xlsx` for a wide-format example.

## Usage

1. **Upload** — Choose your slides (PPT or PDF) and poll responses (Excel). Optionally enter correct answers (e.g. `1,1,0,1` or `A,B,A,C`).
2. **Analytics** — View top 5 performers and per-question engagement charts. Tier counts (Extension / Core / Support) are shown.
3. **Reports** — Click "Generate summary report" to create a topic summary (Word). Click "Generate homework" to create differentiated homework (Extension / Core / Support). Download the .docx files.

## Settings (sidebar)

- **Ollama model** — Model name (e.g. `llama3.2`). Must be pulled with `ollama pull <name>`.
- **Anonymize in report** — Use "Student 1", "Student 2", … instead of names in the top-5 chart.

## Guardrails

- **Local only** — No data is sent to the cloud; Ollama runs on your machine.
- **No PII in prompts** — When generating homework, only topic text and tier counts (e.g. "5 Extension, 12 Core, 4 Support") are sent to the LLM; student names are not included.
- **File limits** — Slides: max 50 MB; Excel: max 10 MB.
- **Disclaimer** — "Analytics and tiers are based only on poll responses; use professional judgment when assigning homework."

## Troubleshooting

- **"Cannot reach Ollama"** — Start Ollama (e.g. run `ollama serve` or open the Ollama app) and ensure a model is pulled (`ollama pull llama3.2`).
- **"Excel must have a column named 'Student Name'"** — Rename your student column to exactly `Student Name` or add that column.
- **No text from slides** — Ensure the file is a valid .pptx or .pdf with selectable text (not only images).

## License

Use and modify as needed for your classroom.
