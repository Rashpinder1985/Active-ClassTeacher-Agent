"""Streamlit UI."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from classroom_report.analytics import (
    chart_engagement,
    chart_score_distribution,
    chart_top_performers,
    parse_optional_band_labels_string,
    parse_responses_bytes,
    parse_score_band_edges_string,
    parse_slides_bytes,
    run_analytics,
)
from classroom_report.badges import build_top_performer_badges_pdf
from classroom_report.config import (
    ALLOWED_EXCEL_EXTENSIONS,
    ALLOWED_SLIDE_EXTENSIONS,
    BADGE_TOP_N,
    MAX_EXCEL_SIZE_BYTES,
    MAX_SLIDES_SIZE_BYTES,
    TOP_PERFORMER_CHART_N,
)
from classroom_report.excel import find_student_name_column
from classroom_report.loaders import combine_agent_skills, load_agent_md, load_skills_md
from classroom_report.ollama import OllamaClient
from classroom_report.reports import build_homework_docx, build_summary_docx


def run_streamlit() -> None:
    st.set_page_config(
        page_title="Classroom Report & Analytics",
        page_icon="📚",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.caption(
        "Analytics and tiers are based only on poll responses; use professional judgment when assigning homework."
    )
    if "band_edges_str" not in st.session_state:
        st.session_state["band_edges_str"] = "0, 40, 50, 70, 80, 100"
    if "band_labels_str" not in st.session_state:
        st.session_state["band_labels_str"] = ""

    def _parse_slides(slide_file):
        if slide_file is None:
            return "", ""
        return parse_slides_bytes(slide_file.name or "slides.pptx", slide_file.getvalue())

    def _parse_responses(excel_file, answer_key):
        return parse_responses_bytes(
            excel_file.getvalue(),
            filename=excel_file.name or "responses.xlsx",
            answer_key=answer_key,
        )

    def _get_slide_file():
        f = st.session_state.get("slide_file")
        if f is not None:
            try:
                f.getvalue()
                return f
            except Exception:
                pass
        raw = st.session_state.get("slide_file_bytes")
        name = st.session_state.get("slide_file_name", "slides.pptx")
        if raw is not None:
            buf = BytesIO(raw)
            buf.name = name
            return buf
        return None

    def _get_excel_file():
        f = st.session_state.get("excel_file")
        if f is not None:
            try:
                f.getvalue()
                return f
            except Exception:
                try:
                    f.seek(0)
                    return f
                except Exception:
                    pass
        raw = st.session_state.get("excel_file_bytes")
        name = st.session_state.get("excel_file_name", "responses.xlsx")
        if raw is not None:
            buf = BytesIO(raw)
            buf.name = name
            return buf
        return None

    def _invalidate_analytics() -> None:
        st.session_state.pop("_analytics_ready", None)

    def _session_score_bands() -> tuple[list[float], list[str] | None]:
        es = st.session_state.get("band_edges_str", "0, 40, 50, 70, 80, 100")
        ls_raw = st.session_state.get("band_labels_str", "") or ""
        edges = parse_score_band_edges_string(es)
        labels = parse_optional_band_labels_string(ls_raw)
        labels_arg: list[str] | None = labels if labels else None
        return edges, labels_arg

    def _ensure_analytics_data():
        if st.session_state.get("_analytics_ready"):
            return None
        excel_file = _get_excel_file()
        if not excel_file:
            return "Upload an Excel file first."
        try:
            size = len(excel_file.getvalue()) if hasattr(excel_file, "getvalue") else getattr(excel_file, "size", 0)
        except Exception:
            size = 0
        if size > MAX_EXCEL_SIZE_BYTES:
            return "Excel file too large."
        try:
            if hasattr(excel_file, "seek"):
                excel_file.seek(0)
            df, q_cols = _parse_responses(excel_file, st.session_state.get("answer_key"))
        except Exception as e:
            return str(e)
        try:
            edges, labels_arg = _session_score_bands()
        except ValueError as e:
            return str(e)
        bundle = run_analytics(
            df,
            q_cols,
            top_chart_n=TOP_PERFORMER_CHART_N,
            score_band_edges=edges,
            score_band_labels=labels_arg,
        )
        st.session_state["responses_df"] = df
        st.session_state["question_columns"] = q_cols
        st.session_state["scores_df"] = bundle.scores_df
        st.session_state["ranked_df"] = bundle.ranked_df
        st.session_state["top_performers_df"] = bundle.top_performers_df
        st.session_state["tier_counts"] = bundle.tier_counts
        st.session_state["show_engagement"] = bundle.show_engagement
        st.session_state["score_stats"] = bundle.score_stats
        st.session_state["band_counts"] = bundle.band_counts
        tpdf = bundle.top_performers_df.head(BADGE_TOP_N)
        nc = find_student_name_column(tpdf) if not tpdf.empty else None
        top5_records: list[dict] = []
        if nc is not None and not tpdf.empty:
            for _, row in tpdf.iterrows():
                rk = row["rank"] if "rank" in tpdf.columns else 0
                top5_records.append(
                    {
                        "Student Name": str(row[nc]),
                        "score_pct": float(row["score_pct"]),
                        "rank": int(rk) if pd.notna(rk) else 0,
                    }
                )
        st.session_state["top_performers_top5"] = top5_records
        st.session_state["_analytics_ready"] = True
        return None

    def _ensure_lecture_data():
        if st.session_state.get("_lecture_ready"):
            return None
        slide_file = _get_slide_file()
        if not slide_file:
            return "Upload slides first."
        if slide_file.size > MAX_SLIDES_SIZE_BYTES:
            return "Slides file too large."
        try:
            lecture_text, poll_text = _parse_slides(slide_file)
        except Exception as e:
            return str(e)
        st.session_state["lecture_text"] = lecture_text
        st.session_state["poll_questions_text"] = poll_text
        st.session_state["_lecture_ready"] = True
        return None

    with st.sidebar:
        st.header("Settings")
        st.text_input("Ollama model", value="llama3.2", key="ollama_model", help="Model pulled via ollama pull <name>")
        st.checkbox("Anonymize in report", value=False, key="anonymize", help="Use 'Student 1' etc. instead of names in outputs")
        st.number_input(
            "Homework validation retries",
            min_value=1,
            max_value=8,
            value=4,
            key="homework_max_attempts",
            help="Model generates homework, then a reviewer checks it; on failure the model retries up to this many times.",
        )
        st.divider()
        st.subheader("File limits")
        st.write(f"Slides: max {MAX_SLIDES_SIZE_BYTES // (1024 * 1024)} MB")
        st.write(f"Excel: max {MAX_EXCEL_SIZE_BYTES // (1024 * 1024)} MB")

    st.title("Classroom Report & Analytics")
    page = st.radio("Go to", ["Upload", "Analytics", "Reports"], horizontal=True, label_visibility="collapsed", key="page_radio")

    if page == "Upload":
        st.header("Upload")
        slide_file = st.file_uploader(
            "Lecture slides (PPT or PDF)",
            type=[e.lstrip(".") for e in ALLOWED_SLIDE_EXTENSIONS],
            help="One file per lecture. Questions do not need to be on slides—upload quiz results in Excel. Optional: title or first line Poll/Question/Quiz for extra summary context.",
            key="slide_upload",
        )
        excel_file = st.file_uploader(
            "Poll / quiz responses (Excel)",
            type=[e.lstrip(".") for e in ALLOWED_EXCEL_EXTENSIONS],
            help="Student row (Name, Email, Roll No, …) plus Q1, Q2, … (1/0); Q1_Selected/Q1_Correct; or a marks/score column (optional Max Marks).",
            key="excel_upload",
        )
        answer_key = st.text_input(
            "Correct answers (optional)",
            placeholder="e.g. 1,1,0,1 or A,B,A,C",
            help="Comma-separated; one value per question. If empty, we assume 1=correct.",
            key="answer_key_input",
        )
        if slide_file:
            if slide_file.size > MAX_SLIDES_SIZE_BYTES:
                st.error(f"Slides file too large. Max {MAX_SLIDES_SIZE_BYTES // (1024 * 1024)} MB.")
            else:
                st.success(f"Slides: {slide_file.name} ({slide_file.size // 1024} KB)")
        if excel_file:
            if excel_file.size > MAX_EXCEL_SIZE_BYTES:
                st.error(f"Excel file too large. Max {MAX_EXCEL_SIZE_BYTES // (1024 * 1024)} MB.")
            else:
                st.success(f"Responses: {excel_file.name} ({excel_file.size // 1024} KB)")

        st.session_state["slide_file"] = slide_file
        st.session_state["excel_file"] = excel_file
        if slide_file is not None:
            st.session_state["slide_file_bytes"] = slide_file.getvalue()
            st.session_state["slide_file_name"] = slide_file.name
        if excel_file is not None:
            st.session_state["excel_file_bytes"] = excel_file.getvalue()
            st.session_state["excel_file_name"] = excel_file.name
        st.session_state["answer_key"] = answer_key.strip() if answer_key else None
        fingerprint = (
            (slide_file.name, slide_file.size) if slide_file else (None, None),
            (excel_file.name, excel_file.size) if excel_file else (None, None),
        )
        if st.session_state.get("_upload_fingerprint") != fingerprint:
            st.session_state["_upload_fingerprint"] = fingerprint
            st.session_state.pop("_lecture_ready", None)
            st.session_state.pop("_analytics_ready", None)

    elif page == "Analytics":
        st.header("Analytics")
        st.caption(
            "Set bin edges from 0 to 100 (comma-separated). Optional: one label per band, same order as bins, comma-separated."
        )
        cbe, cbl = st.columns(2)
        with cbe:
            st.text_input(
                "Score band edges (%)",
                key="band_edges_str",
                help="Must start at 0 and end at 100. Example: 0, 40, 50, 70, 80, 100",
                on_change=_invalidate_analytics,
            )
        with cbl:
            st.text_input(
                "Band labels (optional)",
                key="band_labels_str",
                placeholder="e.g. Low, Mid, High or leave empty for auto labels",
                help="If set, provide one label per score band (number of edges minus one).",
                on_change=_invalidate_analytics,
            )
        err = _ensure_analytics_data()
        if err:
            st.error(err)
            st.info("Upload an Excel file with poll responses on the Upload page first.")
        else:
            responses_df = st.session_state["responses_df"]
            question_columns = st.session_state["question_columns"]
            top_performers_df = st.session_state["top_performers_df"]
            ranked_df = st.session_state["ranked_df"]
            tier_counts = st.session_state["tier_counts"]
            score_stats = st.session_state.get("score_stats") or {}
            band_counts = st.session_state.get("band_counts") or {}
            show_engagement = st.session_state.get("show_engagement", False)

            st.subheader("Class score statistics")
            c0a, c0b, c0c, c0d, c0e, c0f = st.columns(6)
            c0a.metric("Students (n)", score_stats.get("n", 0))
            c0b.metric("Class mean (%)", score_stats.get("mean", 0))
            c0c.metric("Median (%)", score_stats.get("median", 0))
            c0d.metric("Std dev", score_stats.get("std", 0))
            c0e.metric("Min (%)", score_stats.get("min", 0))
            c0f.metric("Max (%)", score_stats.get("max", 0))

            st.plotly_chart(chart_score_distribution(band_counts), use_container_width=True)

            if show_engagement:
                c1, c2 = st.columns(2)
                with c1:
                    fig_top = chart_top_performers(
                        top_performers_df,
                        TOP_PERFORMER_CHART_N,
                        anonymize=st.session_state.get("anonymize", False),
                    )
                    st.plotly_chart(fig_top, use_container_width=True)
                with c2:
                    st.plotly_chart(chart_engagement(responses_df, question_columns), use_container_width=True)
            else:
                st.caption("Per-question engagement (poll) is shown only when the sheet has multiple questions or binary 0/1 items (marks-only sheets use the distribution above).")
                fig_top = chart_top_performers(
                    top_performers_df,
                    TOP_PERFORMER_CHART_N,
                    anonymize=st.session_state.get("anonymize", False),
                )
                st.plotly_chart(fig_top, use_container_width=True)
            st.subheader("Tier counts")
            st.write(
                "Extension (top): ",
                tier_counts.get("top", 0),
                " | Core (average): ",
                tier_counts.get("average", 0),
                " | Support (low): ",
                tier_counts.get("low", 0),
            )
            st.dataframe(
                ranked_df[["Student Name", "score_pct", "tier", "rank"]].head(20),
                use_container_width=True,
                hide_index=True,
            )

    elif page == "Reports":
        st.header("Reports")
        if _get_slide_file() is None or _get_excel_file() is None:
            st.info("Upload both slides and poll responses on the Upload page first.")
        else:
            client = OllamaClient(model=st.session_state.get("ollama_model", "llama3.2"))
            ok, msg = client.available()
            if not ok:
                st.warning(msg)
            else:
                st.success("Ollama is available.")

            _ensure_lecture_data()
            _ensure_analytics_data()
            lecture_text = st.session_state.get("lecture_text", "")
            poll_questions_text = st.session_state.get("poll_questions_text", "")
            tier_counts = st.session_state.get("tier_counts", {})

            st.subheader("Topic summary (Word)")
            if st.button("Generate summary report"):
                if not ok:
                    st.error("Start Ollama and pull a model first.")
                elif not lecture_text:
                    st.error("No text could be extracted from the slides.")
                else:
                    with st.spinner("Generating summary..."):
                        try:
                            summary = client.generate_topic_summary(lecture_text, poll_questions_text)
                            st.session_state["summary_docx_bytes"] = build_summary_docx(summary)
                            st.session_state["summary_text"] = summary
                            st.session_state["summary_generated"] = True
                            st.success("Summary generated.")
                        except Exception as e:
                            st.error(str(e))

            if st.session_state.get("summary_generated") and st.session_state.get("summary_docx_bytes"):
                st.download_button(
                    "Download summary report (.docx)",
                    data=st.session_state["summary_docx_bytes"],
                    file_name="class_topic_summary.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key="dl_summary",
                )

            st.divider()
            st.subheader("Differentiated homework (Word)")
            if not st.session_state.get("summary_text") and st.session_state.get("lecture_text"):
                st.caption("Tip: Generate the topic summary first so homework activities are based on your lecture content.")

            st.markdown("**Generate for levels:**")
            selected_levels = st.multiselect(
                "Choose which level(s) to generate questions for",
                options=["Extension", "Core", "Support"],
                default=["Extension", "Core", "Support"],
                key="hw_levels",
            )
            if not selected_levels:
                st.caption("Select at least one level (Extension, Core, and/or Support).")

            st.markdown("**Activity options** — question types and how many per selected level:")
            col1, col2, col3 = st.columns(3)
            question_specs = []
            with col1:
                include_mcq = st.checkbox("MCQ", value=True, key="hw_include_mcq")
                num_mcq = st.number_input("Number", min_value=1, max_value=15, value=2, key="hw_num_mcq") if include_mcq else 0
                if include_mcq:
                    question_specs.append({"type": "MCQ", "count": num_mcq})
            with col2:
                include_fib = st.checkbox("Fill in the blanks", value=True, key="hw_include_fib")
                num_fib = st.number_input("Number", min_value=1, max_value=15, value=2, key="hw_num_fib") if include_fib else 0
                if include_fib:
                    question_specs.append({"type": "Fill in the blanks", "count": num_fib})
            with col3:
                include_subj = st.checkbox("Subjective questions", value=True, key="hw_include_subj")
                num_subj = st.number_input("Number", min_value=1, max_value=15, value=1, key="hw_num_subj") if include_subj else 0
                if include_subj:
                    question_specs.append({"type": "Subjective questions", "count": num_subj})
            if not question_specs:
                st.caption("Select at least one question type above.")

            extra_ctx = combine_agent_skills(load_agent_md(), load_skills_md())

            if st.button("Generate homework"):
                if not ok:
                    st.error("Start Ollama and pull a model first.")
                elif not selected_levels:
                    st.error("Select at least one level (Extension, Core, and/or Support).")
                elif not question_specs:
                    st.error("Select at least one question type and set the number of questions.")
                else:
                    max_att = int(st.session_state.get("homework_max_attempts", 4))
                    with st.spinner("Generating homework; validating completeness (may retry)..."):
                        try:
                            topic = (st.session_state.get("summary_text") or st.session_state.get("lecture_text", ""))[:6000]
                            homework, val_note = client.generate_homework_until_validated(
                                topic,
                                tier_counts,
                                question_specs=question_specs,
                                levels=selected_levels,
                                extra_system=extra_ctx or None,
                                max_attempts=max_att,
                            )
                            st.session_state["homework_docx_bytes"] = build_homework_docx(homework)
                            st.session_state["homework_text"] = homework
                            st.session_state["homework_validation_note"] = val_note
                            st.session_state["homework_generated"] = True
                            st.success(f"Homework generated. {val_note}")
                        except ValueError as e:
                            st.session_state.pop("homework_generated", None)
                            st.session_state.pop("homework_docx_bytes", None)
                            st.session_state.pop("homework_validation_note", None)
                            st.error(str(e))
                        except Exception as e:
                            st.error(str(e))

            if st.session_state.get("homework_validation_note"):
                st.caption(st.session_state["homework_validation_note"])

            if st.session_state.get("homework_generated") and st.session_state.get("homework_docx_bytes"):
                st.download_button(
                    "Download homework (.docx)",
                    data=st.session_state["homework_docx_bytes"],
                    file_name="differentiated_homework.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key="dl_homework",
                )

            st.divider()
            st.subheader("Top performer badges (PDF)")
            st.caption(
                "One landscape page per student (top five scores). Each badge includes a unique motivational quote. "
                "Respects anonymize setting for names."
            )
            top5 = st.session_state.get("top_performers_top5") or []
            if not top5:
                st.info("Run analytics with responses data to load top performers, or ensure at least one student row exists.")
            elif st.button("Generate top performer badges", key="gen_badges"):
                if not ok:
                    st.error("Start Ollama and pull a model first.")
                else:
                    with st.spinner("Creating quotes and PDF badges..."):
                        try:
                            names: list[str] = []
                            scores: list[float] = []
                            for i, row in enumerate(top5):
                                nm = str(row.get("Student Name", ""))
                                if st.session_state.get("anonymize"):
                                    nm = f"Student {i + 1}"
                                names.append(nm or f"Student {i + 1}")
                                try:
                                    scores.append(float(row.get("score_pct", 0)))
                                except (TypeError, ValueError):
                                    scores.append(0.0)
                            quotes = client.generate_quotes_for_badges(names, scores, extra_system=extra_ctx or None)
                            pdf_bytes = build_top_performer_badges_pdf(list(zip(names, scores, quotes)))
                            st.session_state["badge_pdf_bytes"] = pdf_bytes
                            st.session_state["badges_generated"] = True
                            st.success("Badges PDF ready.")
                        except Exception as e:
                            st.error(str(e))

            if st.session_state.get("badges_generated") and st.session_state.get("badge_pdf_bytes"):
                st.download_button(
                    "Download top performer badges (.pdf)",
                    data=st.session_state["badge_pdf_bytes"],
                    file_name="top_performer_badges.pdf",
                    mime="application/pdf",
                    key="dl_badges",
                )
