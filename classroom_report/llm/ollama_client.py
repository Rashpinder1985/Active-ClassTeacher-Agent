"""Ollama client: prompt to string with connection checks."""
import os
from typing import Optional

from classroom_report.config import OLLAMA_HOST


def get_ollama_host() -> str:
    return os.environ.get("OLLAMA_HOST", OLLAMA_HOST)


def check_ollama_available(host: Optional[str] = None) -> tuple[bool, str]:
    """
    Ping Ollama (e.g. GET /api/tags). Returns (success, message).
    """
    import urllib.request
    import urllib.error

    base = (host or get_ollama_host()).rstrip("/")
    url = f"{base}/api/tags"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as r:
            if r.status == 200:
                return True, "Ollama is available."
            return False, f"Ollama returned status {r.status}"
    except urllib.error.URLError as e:
        return False, f"Cannot reach Ollama: {e.reason}. Start Ollama and pull a model (e.g. ollama pull llama3.2)."
    except Exception as e:
        return False, str(e)


def prompt_ollama(
    prompt: str,
    model: str = "llama3.2",
    host: Optional[str] = None,
    system: Optional[str] = None,
) -> str:
    """
    Send prompt to Ollama chat API; return assistant message content.
    Raises RuntimeError if Ollama is unavailable or returns an error.
    """
    try:
        from ollama import chat
    except ImportError:
        raise ImportError("ollama package required. Install with: pip install ollama")

    base = host or get_ollama_host()
    # ollama package uses OLLAMA_HOST env
    env_host = os.environ.get("OLLAMA_HOST")
    try:
        if base:
            os.environ["OLLAMA_HOST"] = base
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = chat(model=model, messages=messages)
        content = getattr(response, "message", None) or (response if isinstance(response, dict) else {})
        if hasattr(content, "content"):
            return content.content or ""
        if isinstance(content, dict) and "content" in content:
            return content.get("content", "") or ""
        return str(content)
    finally:
        if env_host is not None:
            os.environ["OLLAMA_HOST"] = env_host
        elif "OLLAMA_HOST" in os.environ and not base:
            del os.environ["OLLAMA_HOST"]


class OllamaClient:
    """Thin wrapper for summary and homework generation."""

    def __init__(self, model: str = "llama3.2", host: Optional[str] = None):
        self.model = model
        self.host = host or get_ollama_host()

    def available(self) -> tuple[bool, str]:
        return check_ollama_available(self.host)

    def generate_topic_summary(
        self,
        lecture_text: str,
        poll_questions_text: str = "",
        extra_system: Optional[str] = None,
    ) -> str:
        """Generate 1–2 paragraph topic summary from lecture and optional poll questions."""
        system = "You are a helpful assistant that writes concise, factual summaries for teachers."
        if extra_system and extra_system.strip():
            system = system + "\n\n" + extra_system.strip()
        prompt = (
            "Based on the following lecture content, write a short topic summary (1–2 paragraphs) "
            "suitable for a class report. Be concise and focus on the main concepts discussed.\n\n"
            "Lecture content:\n" + lecture_text
        )
        if poll_questions_text:
            prompt += "\n\nPoll questions covered:\n" + poll_questions_text
        prompt += "\n\nWrite only the summary, no headings."
        return prompt_ollama(prompt, model=self.model, host=self.host, system=system)

    def generate_differentiated_homework(
        self,
        topic_summary: str,
        tier_counts: dict[str, int],
        question_specs: Optional[list[dict]] = None,
        levels: Optional[list[str]] = None,
        extra_system: Optional[str] = None,
    ) -> str:
        """
        Generate differentiated homework based on lecture/PPT content.
        tier_counts: {'top': n, 'average': n, 'low': n}.
        question_specs: optional list of {"type": "MCQ"|"Fill in the blanks"|"Subjective questions", "count": n}.
        levels: list of level names to generate, e.g. ["Extension", "Core", "Support"] or ["Core"] only.
        Answer key for MCQs must be at the end, not inline.
        """
        if not (topic_summary or "").strip():
            return (
                "Extension\n\nBased on today's class, complete 2–3 extension tasks that go beyond the lesson.\n\n"
                "Core\n\nComplete the standard practice set based on today's topic.\n\n"
                "Support\n\nWork through the guided practice and review the key points from class.\n\n"
                "Answer key\n\n(MCQ answers listed here when generated.)"
            )
        specs = question_specs or [
            {"type": "MCQ", "count": 2},
            {"type": "Fill in the blanks", "count": 2},
            {"type": "Subjective questions", "count": 1},
        ]
        levels = levels or ["Extension", "Core", "Support"]
        spec_text = ", ".join(f"{s['count']} {s['type']}" for s in specs)
        levels_text = ", ".join(levels)

        system = (
            "You are a helpful assistant for teachers. You generate concrete homework activities. "
            "Do not mention student names or performance levels. "
            "Use only the section headings requested (Extension, Core, Support). "
            "For MCQs: give question and 4 options (A, B, C, D) only — do NOT write the correct answer next to the question. "
            "Put all MCQ correct answers in a separate 'Answer key' section at the very end of your output."
        )
        if extra_system and extra_system.strip():
            system = system + "\n\n" + extra_system.strip()
        prompt = (
            "Use the following lecture/topic content to generate differentiated homework.\n\n"
            "---\nLECTURE / TOPIC CONTENT\n---\n\n"
            + topic_summary.strip()
            + "\n\n---\n"
            "Generate ONLY these sections (in this order): " + levels_text + ".\n\n"
            f"For EACH of these sections, generate exactly: {spec_text}.\n\n"
            "Requirements:\n"
            "- MCQ: write the question and four options (A, B, C, D). Do NOT indicate the correct answer in the question. "
            "At the very end of your output, add a section titled exactly 'Answer key' (or 'Answer Key') and list only the correct answers for every MCQ, "
            "e.g. 'Extension: 1. A, 2. C | Core: 1. B, 2. D | Support: 1. A' or similar so the teacher can use it for grading.\n"
            "- Fill in the blanks: write a sentence with ____ for the blank; base the word on the lecture.\n"
            "- Subjective questions: open-ended questions for a short paragraph or list answer.\n"
            "Extension: slightly harder or extension-oriented. Core: standard difficulty. Support: simpler and more guided.\n\n"
            f"Output format: put each of these headings on its own line: {levels_text}. Under each heading list the questions. "
            "After all level sections, add the 'Answer key' section. Do not output anything before the first heading or after Answer key."
        )
        return prompt_ollama(prompt, model=self.model, host=self.host, system=system)
