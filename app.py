"""
Classroom Report & Analytics — Streamlit entry point.
Local-only app: upload slides (PPT/PDF) + poll responses (Excel),
generate topic summary, poll analytics, and differentiated homework.
"""
from io import BytesIO

import streamlit as st

from config import (
    ALLOWED_EXCEL_EXTENSIONS,
    ALLOWED_SLIDE_EXTENSIONS,
    MAX_EXCEL_SIZE_BYTES,
    MAX_SLIDES_SIZE_BYTES,
)

# Page config
st.set_page_config(
    page_title="Classroom Report & Analytics",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Guardrail disclaimer (always visible)
st.caption(
    "Analytics and tiers are based only on poll responses; use professional judgment when assigning homework."
)


def _parse_slides(slide_file):
    """Return (lecture_text, poll_questions_text) from uploaded slide file."""
    if slide_file is None:
        return "", ""
    ext = slide_file.name.lower().split(".")[-1] if slide_file.name else ""
    buf = BytesIO(slide_file.getvalue())
    if ext == "pptx":
        from parsers.slides_pptx import extract_text_from_pptx, get_poll_slides
        full_text, slides_text = extract_text_from_pptx(buf)
    elif ext == "pdf":
        from parsers.slides_pdf import extract_text_from_pdf, get_poll_slides
        full_text, slides_text = extract_text_from_pdf(buf)
    else:
        return "", ""
    poll_slides = get_poll_slides(slides_text)
    poll_text = "\n\n".join([f"Slide {i}: {t}" for i, t in poll_slides]) if poll_slides else ""
    return full_text, poll_text


def _parse_responses(excel_file, answer_key):
    """Load Excel and return (df, question_columns). Raises on error."""
    from parsers.responses import load_responses, normalize_responses
    df = load_responses(excel_file, answer_key=answer_key)
    df, q_cols = normalize_responses(df)
    return df, q_cols


def _ensure_analytics_data():
    """Parse uploads and compute analytics; store in session_state. Returns error message or None."""
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
    from analytics.scoring import compute_scores, assign_tiers, get_top_n
    scores_df = compute_scores(df, q_cols)
    ranked_df = assign_tiers(scores_df)
    top5_df = get_top_n(ranked_df, 5)
    tier_counts = ranked_df["tier"].value_counts().to_dict() if "tier" in ranked_df.columns else {}
    st.session_state["responses_df"] = df
    st.session_state["question_columns"] = q_cols
    st.session_state["scores_df"] = scores_df
    st.session_state["ranked_df"] = ranked_df
    st.session_state["top5_df"] = top5_df
    st.session_state["tier_counts"] = tier_counts
    st.session_state["_analytics_ready"] = True
    return None


def _ensure_lecture_data():
    """Parse slides and store lecture_text, poll_questions_text. Returns error or None."""
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


# Sidebar: config
with st.sidebar:
    st.header("Settings")
    ollama_model = st.text_input("Ollama model", value="llama3.2", key="ollama_model", help="Model pulled via ollama pull <name>")
    anonymize = st.checkbox("Anonymize in report", value=False, key="anonymize", help="Use 'Student 1' etc. instead of names in outputs")
    st.divider()
    st.subheader("File limits")
    st.write(f"Slides: max {MAX_SLIDES_SIZE_BYTES // (1024*1024)} MB")
    st.write(f"Excel: max {MAX_EXCEL_SIZE_BYTES // (1024*1024)} MB")

# Navigation: pages
st.title("Classroom Report & Analytics")

page = st.radio(
    "Go to",
    ["Upload", "Analytics", "Reports"],
    horizontal=True,
    label_visibility="collapsed",
    key="page_radio",
)


def _get_slide_file():
    """Return the uploaded slide file (from widget or from persisted bytes)."""
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
    """Return the uploaded Excel file (from widget or from persisted bytes)."""
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


if page == "Upload":
    st.header("Upload")
    slide_file = st.file_uploader(
        "Lecture slides (PPT or PDF)",
        type=[e.lstrip(".") for e in ALLOWED_SLIDE_EXTENSIONS],
        help="One file per lecture. Poll questions can be on slides titled 'Poll' or 'Question'.",
        key="slide_upload",
    )
    excel_file = st.file_uploader(
        "Poll responses (Excel)",
        type=[e.lstrip(".") for e in ALLOWED_EXCEL_EXTENSIONS],
        help="Student Name + Q1, Q2, ... (1/0) OR Student Name + Q1_Selected/Q1_Correct, Q2_Selected/Q2_Correct, ... (letters A–D).",
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
            st.error(f"Slides file too large. Max {MAX_SLIDES_SIZE_BYTES // (1024*1024)} MB.")
        else:
            st.success(f"Slides: {slide_file.name} ({slide_file.size // 1024} KB)")
    if excel_file:
        if excel_file.size > MAX_EXCEL_SIZE_BYTES:
            st.error(f"Excel file too large. Max {MAX_EXCEL_SIZE_BYTES // (1024*1024)} MB.")
        else:
            st.success(f"Responses: {excel_file.name} ({excel_file.size // 1024} KB)")

    # Persist in session state for other pages; save bytes so uploads survive when user switches to Analytics/Reports
    st.session_state["slide_file"] = slide_file
    st.session_state["excel_file"] = excel_file
    if slide_file is not None:
        st.session_state["slide_file_bytes"] = slide_file.getvalue()
        st.session_state["slide_file_name"] = slide_file.name
    if excel_file is not None:
        st.session_state["excel_file_bytes"] = excel_file.getvalue()
        st.session_state["excel_file_name"] = excel_file.name
    st.session_state["answer_key"] = answer_key.strip() if answer_key else None
    # Invalidate caches when files change
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
    err = _ensure_analytics_data()
    if err:
        st.error(err)
        st.info("Upload an Excel file with poll responses on the Upload page first.")
    else:
        responses_df = st.session_state["responses_df"]
        question_columns = st.session_state["question_columns"]
        top5_df = st.session_state["top5_df"]
        ranked_df = st.session_state["ranked_df"]
        tier_counts = st.session_state["tier_counts"]

        from analytics.charts import chart_top5, chart_engagement

        c1, c2 = st.columns(2)
        with c1:
            fig_top5 = chart_top5(top5_df, anonymize=st.session_state.get("anonymize", False))
            st.plotly_chart(fig_top5, use_container_width=True)
        with c2:
            fig_eng = chart_engagement(responses_df, question_columns)
            st.plotly_chart(fig_eng, use_container_width=True)

        st.subheader("Tier counts")
        st.write("Extension (top): ", tier_counts.get("top", 0), " | Core (average): ", tier_counts.get("average", 0), " | Support (low): ", tier_counts.get("low", 0))
        st.dataframe(ranked_df[["Student Name", "score_pct", "tier", "rank"]].head(20), use_container_width=True, hide_index=True)

elif page == "Reports":
    st.header("Reports")
    if _get_slide_file() is None or _get_excel_file() is None:
        st.info("Upload both slides and poll responses on the Upload page first.")
    else:
        from llm.ollama_client import OllamaClient, check_ollama_available
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

        # Generate Summary
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
                        from reports.summary_doc import build_summary_docx
                        doc_bytes = build_summary_docx(summary)
                        st.session_state["summary_docx_bytes"] = doc_bytes
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

        # Level(s) to generate
        st.markdown("**Generate for levels:**")
        levels_options = ["Extension", "Core", "Support"]
        selected_levels = st.multiselect(
            "Choose which level(s) to generate questions for",
            options=levels_options,
            default=levels_options,
            key="hw_levels",
        )
        if not selected_levels:
            st.caption("Select at least one level (Extension, Core, and/or Support).")

        # Homework options: question types and counts per type
        st.markdown("**Activity options** — question types and how many per selected level:")
        col1, col2, col3 = st.columns(3)
        question_specs = []
        with col1:
            include_mcq = st.checkbox("MCQ", value=True, key="hw_include_mcq")
            num_mcq = st.number_input("Number", min_value=1, max_value=15, value=3, key="hw_num_mcq") if include_mcq else 0
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

        if st.button("Generate homework"):
            if not ok:
                st.error("Start Ollama and pull a model first.")
            elif not selected_levels:
                st.error("Select at least one level (Extension, Core, and/or Support).")
            elif not question_specs:
                st.error("Select at least one question type and set the number of questions.")
            else:
                with st.spinner("Generating homework..."):
                    try:
                        topic = st.session_state.get("summary_text") or st.session_state.get("lecture_text", "")
                        topic = (topic or "")[:6000]
                        homework = client.generate_differentiated_homework(
                            topic, tier_counts, question_specs=question_specs, levels=selected_levels
                        )
                        from reports.homework_doc import build_homework_docx
                        doc_bytes = build_homework_docx(homework)
                        st.session_state["homework_docx_bytes"] = doc_bytes
                        st.session_state["homework_generated"] = True
                        st.success("Homework generated.")
                    except Exception as e:
                        st.error(str(e))

        if st.session_state.get("homework_generated") and st.session_state.get("homework_docx_bytes"):
            st.download_button(
                "Download homework (.docx)",
                data=st.session_state["homework_docx_bytes"],
                file_name="differentiated_homework.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="dl_homework",
            )
