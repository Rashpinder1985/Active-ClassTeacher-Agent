"""CLI entry: run the graph and write outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from classroom_report.graph import invoke_classroom


def cli_main() -> None:
    p = argparse.ArgumentParser(description="Classroom report agent (LangGraph + Ollama)")
    p.add_argument("slides", type=Path, help="Path to lecture slides (.pptx or .pdf)")
    p.add_argument("excel", type=Path, help="Path to poll responses (.xlsx)")
    p.add_argument("--answer-key", default=None, help="Comma-separated correct answers")
    p.add_argument("--ollama-model", default="llama3.2")
    p.add_argument("--no-summary", action="store_true")
    p.add_argument("--no-homework", action="store_true")
    p.add_argument("--anonymize", action="store_true")
    p.add_argument("--out-dir", type=Path, default=Path("."), help="Where to write .docx outputs")
    p.add_argument("--homework-levels", default='["Support", "Core", "Extension"]', help="JSON array of levels (ordered Support→Core→Extension)")
    p.add_argument(
        "--question-specs",
        default='[{"type": "MCQ", "count": 2}, {"type": "Fill in the blanks", "count": 2}, {"type": "Subjective questions", "count": 1}]',
        help="JSON array of {type, count} objects",
    )
    p.add_argument(
        "--score-band-edges",
        default=None,
        help='Optional JSON array of band edges from 0 to 100, e.g. [0,40,50,70,80,100]',
    )
    p.add_argument(
        "--score-band-labels",
        default=None,
        help="Optional JSON array of labels (one per band). Omit to auto-generate labels.",
    )
    p.add_argument("--no-badges", action="store_true", help="Skip top-performer badge PDF")
    p.add_argument(
        "--homework-max-attempts",
        type=int,
        default=4,
        help="Max homework generation+validation rounds (default 4)",
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
        sbe = json.loads(args.score_band_edges) if args.score_band_edges else None
        sbl = json.loads(args.score_band_labels) if args.score_band_labels else None
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    score_band_edges = [float(x) for x in sbe] if isinstance(sbe, list) and len(sbe) >= 2 else None
    score_band_labels = [str(x) for x in sbl] if isinstance(sbl, list) and len(sbl) > 0 else None

    state = invoke_classroom(
        slides_bytes=args.slides.read_bytes(),
        excel_bytes=args.excel.read_bytes(),
        slides_filename=args.slides.name,
        excel_filename=args.excel.name,
        answer_key=args.answer_key,
        ollama_model=args.ollama_model,
        want_summary=not args.no_summary,
        want_homework=not args.no_homework,
        anonymize=args.anonymize,
        homework_levels=levels if isinstance(levels, list) else None,
        question_specs=specs if isinstance(specs, list) else None,
        score_band_edges=score_band_edges,
        score_band_labels=score_band_labels,
        want_badges=not args.no_badges,
        homework_max_attempts=max(1, args.homework_max_attempts),
    )
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    errs = state.get("errors") or []
    for e in errs:
        print(f"Error: {e}", file=sys.stderr)
    if state.get("summary_docx_bytes"):
        pth = out / "class_topic_summary.docx"
        pth.write_bytes(state["summary_docx_bytes"])
        print(f"Wrote {pth}")
    if state.get("homework_docx_bytes"):
        pth = out / "differentiated_homework.docx"
        pth.write_bytes(state["homework_docx_bytes"])
        print(f"Wrote {pth}")
    if state.get("homework_validation_note"):
        print(f"Homework validation: {state['homework_validation_note']}")
    if state.get("badge_pdf_bytes"):
        pth = out / "top_performer_badges.pdf"
        pth.write_bytes(state["badge_pdf_bytes"])
        print(f"Wrote {pth}")
    if state.get("charts"):
        cd = out / "charts"
        cd.mkdir(parents=True, exist_ok=True)
        for name, fig_json in (state.get("charts") or {}).items():
            (cd / f"{name}.json").write_text(fig_json, encoding="utf-8")
        print(f"Wrote Plotly JSON under {cd}")
    preview = state.get("ranked_preview") or []
    if preview:
        print("\nRanked preview (first rows):", json.dumps(preview[:5], indent=2))
    sys.exit(1 if errs else 0 if state.get("ingest_ok") else 1)
