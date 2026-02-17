"""Extract text from PDF files."""
import tempfile
from io import BytesIO
from pathlib import Path
from typing import List, Tuple, Union

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore


def extract_text_from_pdf(path: Union[str, Path, BytesIO]) -> Tuple[str, List[Tuple[int, str]]]:
    """
    Extract all text from a PDF file (path or BytesIO). One page = one "slide".
    Returns (full_lecture_text, list of (page_number_1based, page_text)).
    """
    if fitz is None:
        raise ImportError("PyMuPDF is required for PDF support. Install with: pip install PyMuPDF")
    if isinstance(path, BytesIO):
        doc = fitz.open(stream=path.getvalue(), filetype="pdf")
    else:
        path = Path(path)
        if path.suffix.lower() != ".pdf":
            raise ValueError("File must be .pdf")
        doc = fitz.open(str(path))
    slides_text: List[Tuple[int, str]] = []
    all_parts: List[str] = []
    try:
        for i in range(len(doc)):
            page = doc[i]
            text = page.get_text().strip()
            slides_text.append((i + 1, text))
            if text:
                all_parts.append(text)
    finally:
        doc.close()
    full_text = "\n\n".join(all_parts)
    return full_text, slides_text


def get_poll_slides(slides_text: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
    """Return slides/pages that look like poll/question (first line contains keyword)."""
    poll_keywords = ("poll", "question", "quiz")
    result = []
    for idx, text in slides_text:
        first_line = (text.split("\n")[0] or "").strip().lower()
        if any(kw in first_line for kw in poll_keywords):
            result.append((idx, text))
    return result
