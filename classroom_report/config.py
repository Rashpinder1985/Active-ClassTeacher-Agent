"""Application constants and environment defaults."""

from __future__ import annotations

import os

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")

TIER_TOP_PCT = 20
TIER_AVERAGE_PCT = 60
TIER_LOW_PCT = 20

TOP_PERFORMER_CHART_N = 10
BADGE_TOP_N = 5

MAX_SLIDES_SIZE_BYTES = 50 * 1024 * 1024
MAX_EXCEL_SIZE_BYTES = 10 * 1024 * 1024

ALLOWED_SLIDE_EXTENSIONS = (".pptx", ".pdf")
ALLOWED_EXCEL_EXTENSIONS = (".xlsx", ".xls")

# Canonical column in normalized DataFrames (charts / analytics); source may be Name, Email, Roll, etc.
STUDENT_NAME_COLUMN = "Student Name"

# Exact header matches (lowercase) for student row labels — tried in order
IDENTIFIER_COLUMN_NAMES: tuple[str, ...] = (
    "student name",
    "name",
    "full name",
    "learner",
    "learner name",
    "student",
    "email",
    "e-mail",
    "email id",
    "mail id",
    "mail",
    "roll no",
    "roll number",
    "roll no.",
    "roll",
    "rollno",
    "registration no",
    "reg no",
    "reg. no",
    "registration number",
    "enrollment no",
    "enrolment no",
    "admission no",
    "admission number",
    "student id",
    "student no",
    "sr no",
    "s.no",
    "s. no",
    "serial no",
    "serial number",
    "id",
)

# Substrings (lowercase) — if no exact match, first column whose header contains one of these
IDENTIFIER_HEADER_SUBSTRINGS: tuple[str, ...] = (
    "student name",
    "full name",
    "learner",
    "email",
    "e-mail",
    "mail",
    "roll",
    "registration",
    "enrollment",
    "admission",
    "serial",
)

TOTAL_MARKS_COLUMN_NAMES = (
    "total marks",
    "total mark",
    "total score",
    "marks obtained",
    "obtained marks",
    "score obtained",
    "obtained score",
    "marks scored",
    "final marks",
    "final score",
    "grand total",
    "total obtained",
    "marks",
    "score",
    "grade",
    "points",
    "percentage",
    "percent",
    "%",
    "gpa",
    "cgpa",
)
MAX_MARKS_COLUMN_NAMES = (
    "max marks",
    "max mark",
    "max score",
    "full marks",
    "out of",
    "total possible",
    "maximum marks",
    "maximum score",
)

TIER_LABELS = {"top": "Extension", "average": "Core", "low": "Support"}

# Homework document order: Support → Core → Extension, then Answer key (Support → Core → Extension within key).
HOMEWORK_LEVEL_ORDER: tuple[str, ...] = ("Support", "Core", "Extension")


def normalize_homework_levels(levels: list[str] | None) -> list[str]:
    """Return selected levels in canonical order: Support, Core, Extension."""
    if not levels:
        return list(HOMEWORK_LEVEL_ORDER)
    mapping = {"support": "Support", "core": "Core", "extension": "Extension"}
    seen: list[str] = []
    for raw in levels:
        key = str(raw).strip().lower()
        if key in mapping:
            c = mapping[key]
            if c not in seen:
                seen.append(c)
    if not seen:
        return list(HOMEWORK_LEVEL_ORDER)
    idx = {name: i for i, name in enumerate(HOMEWORK_LEVEL_ORDER)}
    return sorted(seen, key=lambda x: idx[x])
