"""Parsers for slides (PPT/PDF) and poll responses (Excel)."""
from .slides_pptx import extract_text_from_pptx
from .slides_pdf import extract_text_from_pdf
from .responses import load_responses, normalize_responses

__all__ = [
    "extract_text_from_pptx",
    "extract_text_from_pdf",
    "load_responses",
    "normalize_responses",
]
