"""CLI: run the LangGraph classroom pipeline on local files."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from classroom_report.agent import invoke_classroom


def main() -> None:
    p = argparse.ArgumentParser(description="Classroom report agent (LangGraph + Ollama)")
    p.add_argument("slides", type=Path, help="Path to lecture slides (.pptx or .pdf)")
    p.add_argument("excel", type=Path, help="Path to poll responses (.xlsx)")
    p.add_argument("--answer-key", default=None, help="Comma-separated correct answers")
    p.add_argument("--ollama-model", default="llama3.2")
    p.add_argument("--no-summary", action="store_true")
    p.add_argument("--no-homework", action="store_true")
    p.add_argument("--anonymize", action="store_true")
    p.add_argument("--out-dir", type=Path, default=Path("."), help="Where to write .docx outputs")
    p.add_argument(
        "--homework-levels",
        default='["Extension", "Core", "Support"]',
        help='JSON array of levels, e.g. \'["Extension","Core"]\'',
    )
    p.add_argument(
        "--question-specs",
        default='[{"type": "MCQ", "count": 3}, {"type": "Fill in the blanks", "count": 2}, {"type": "Subjective questions", "count": 1}]',
        help="JSON array of {type, count} objects",
    )
    args = p.parse_args()

    if not args.slides.is_file():
        print(f"Slides not found: {args.slides}", file=sys.stderr)
        sys.exit(1)
    if not args.excel.is_file():
        print(f"Excel not found: {args.excel}", file=sys.stderr)
        sys.exit(1)

    try:
        levels = json.loads(args.homework_levels)
        specs = json.loads(args.question_specs)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    slides_bytes = args.slides.read_bytes()
    excel_bytes = args.excel.read_bytes()

    state = invoke_classroom(
        slides_bytes=slides_bytes,
        excel_bytes=excel_bytes,
        slides_filename=args.slides.name,
        excel_filename=args.excel.name,
        answer_key=args.answer_key,
        ollama_model=args.ollama_model,
        want_summary=not args.no_summary,
        want_homework=not args.no_homework,
        anonymize=args.anonymize,
        homework_levels=levels if isinstance(levels, list) else None,
        question_specs=specs if isinstance(specs, list) else None,
    )

    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    errs = state.get("errors") or []
    if errs:
        for e in errs:
            print(f"Error: {e}", file=sys.stderr)

    if state.get("summary_docx_bytes"):
        path = out / "class_topic_summary.docx"
        path.write_bytes(state["summary_docx_bytes"])
        print(f"Wrote {path}")

    if state.get("homework_docx_bytes"):
        path = out / "differentiated_homework.docx"
        path.write_bytes(state["homework_docx_bytes"])
        print(f"Wrote {path}")

    if state.get("charts"):
        charts_dir = out / "charts"
        charts_dir.mkdir(parents=True, exist_ok=True)
        for name, fig_json in (state.get("charts") or {}).items():
            (charts_dir / f"{name}.json").write_text(fig_json, encoding="utf-8")
        print(f"Wrote Plotly JSON under {charts_dir}")

    preview = state.get("ranked_preview") or []
    if preview:
        print("\nRanked preview (first rows):", json.dumps(preview[:5], indent=2))

    if state.get("ingest_ok") and not errs:
        sys.exit(0)
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
