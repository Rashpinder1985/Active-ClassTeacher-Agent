"""Streamlit entrypoint — ``uv run streamlit run app.py``."""
# Load UI only when Streamlit (or `python app.py`) runs this file as the main script,
# so `import app` does not execute Streamlit widgets.
if __name__ == "__main__":
    import classroom_report.streamlit_app  # noqa: F401
