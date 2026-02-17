"""Report generation: summary and homework .docx."""
from .summary_doc import build_summary_docx
from .homework_doc import build_homework_docx

__all__ = ["build_summary_docx", "build_homework_docx"]
