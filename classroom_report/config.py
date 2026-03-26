"""Configuration defaults for the Classroom Report & Analytics app."""
import os

# Ollama
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")

# Tier thresholds (percentiles): top %, middle %, low %
TIER_TOP_PCT = 20
TIER_AVERAGE_PCT = 60
TIER_LOW_PCT = 20

# File size limits (bytes)
MAX_SLIDES_SIZE_BYTES = 50 * 1024 * 1024   # 50 MB
MAX_EXCEL_SIZE_BYTES = 10 * 1024 * 1024   # 10 MB

# Allowed extensions
ALLOWED_SLIDE_EXTENSIONS = (".pptx", ".pdf")
ALLOWED_EXCEL_EXTENSIONS = (".xlsx", ".xls")

# Excel column name for student identity (case-insensitive match)
STUDENT_NAME_COLUMN = "Student Name"

# Neutral tier labels for homework doc (pedagogical guardrail)
TIER_LABELS = {
    "top": "Extension",
    "average": "Core",
    "low": "Support",
}
