"""Public entrypoint: `uvicorn app:api_app`, `streamlit run app.py`, `classroom` CLI."""

from __future__ import annotations

import sys

from classroom_report.api import api_app
from classroom_report.cli import cli_main
from classroom_report.streamlit_app import run_streamlit

__all__ = ["api_app", "cli_main", "run_streamlit"]

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        cli_main()
    else:
        run_streamlit()
