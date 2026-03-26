"""Ollama HTTP client for topic summary and homework."""

from __future__ import annotations

import os
import re
import urllib.error
import urllib.request
from typing import Optional

from classroom_report.config import OLLAMA_HOST

FALLBACK_BADGE_QUOTES: tuple[str, ...] = (
    "Your effort is showing—keep that momentum going.",
    "Every step forward counts; you proved it today.",
    "Curiosity and grit—keep combining them like this.",
    "Strong work—build on this win next lesson.",
    "You rose to the challenge—stay proud and stay hungry.",
)


def get_ollama_host() -> str:
    return os.environ.get("OLLAMA_HOST", OLLAMA_HOST)


def check_ollama_available(host: Optional[str] = None) -> tuple[bool, str]:
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
    from ollama import chat

    base = host or get_ollama_host()
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
        revision_feedback: Optional[str] = None,
    ) -> str:
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

        def _count_for_type(specs: list[dict], needle: str) -> int:
            for s in specs:
                if needle in str(s.get("type", "")):
                    return int(s.get("count", 0))
            return 0

        n_mcq = _count_for_type(specs, "MCQ")
        n_fill = _count_for_type(specs, "Fill")
        n_subj = _count_for_type(specs, "Subjective")

        per_section_parts: list[str] = []
        if n_mcq > 0:
            per_section_parts.append(
                f"at least {n_mcq} objective MCQ(s) (each with four options A, B, C, D; do not mark the correct in the question)"
            )
        if n_fill > 0:
            per_section_parts.append(f"at least {n_fill} fill-in-the-blank(s) (sentence with ____ for the blank)")
        if n_subj > 0:
            per_section_parts.append(f"at least {n_subj} subjective short-answer question(s).")
        per_section_rule = (
            "For EACH section (" + levels_text + "), include: " + "; ".join(per_section_parts)
            if per_section_parts
            else ""
        )

        system = (
            "You are a helpful assistant for teachers. You generate concrete homework activities. "
            "Do not mention student names or performance levels. "
            "Use only the section headings requested (Extension, Core, Support). "
            "For MCQs: give question and 4 options (A, B, C, D) only — do NOT write the correct answer next to the question. "
            "Put all MCQ correct answers in a separate 'Answer key' section at the very end of your output."
        )
        if extra_system and extra_system.strip():
            system = system + "\n\n" + extra_system.strip()
        revision_block = ""
        if revision_feedback and revision_feedback.strip():
            revision_block = revision_feedback.strip() + "\n\n---\n\n"
        prompt = (
            revision_block
            + "Use the following lecture/topic content to generate differentiated homework.\n\n"
            "---\nLECTURE / TOPIC CONTENT\n---\n\n"
            + topic_summary.strip()
            + "\n\n---\n"
            "Generate ONLY these sections (in this order): " + levels_text + ".\n\n"
            f"Target totals (for reference when planning each section): {spec_text}.\n\n"
            "**CRITICAL:** Each section must be self-contained. Under each heading (Extension, Core, Support) that you output, "
            "you must include every question type listed below—do not satisfy the counts only by spreading types across "
            "different sections (e.g. all MCQs in Extension only). "
            + per_section_rule
            + "\n\n"
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

    def review_homework_completeness(
        self,
        homework_text: str,
        levels: list[str],
        question_specs: list[dict],
    ) -> tuple[bool, str]:
        """LLM check that homework matches requested levels and per-type counts."""
        if not (homework_text or "").strip():
            return False, "Homework text is empty."
        spec_lines = "\n".join(
            f"- {int(s.get('count', 0))} × {s.get('type', '')}" for s in question_specs
        )
        levels_line = ", ".join(levels)
        system = (
            "You are a strict QA reviewer for teacher homework drafts. "
            "Be concise. Respond with exactly two lines: line 1 is PASS or FAIL; line 2 explains if FAIL, or OK if PASS."
        )
        prompt = f"""The teacher required these sections (headings): {levels_line}.
Minimum items per section (per type; if a type has count 0, ignore that type):
{spec_lines}

Verify the homework text below:
- Each required section heading exists and is clearly labeled.
- Under EACH section, each question type with count > 0 appears enough times (MCQs with A/B/C/D options; fill-ins with ____; subjective as open prompts).
- If any MCQs exist, there must be an Answer key section at the end.

---
HOMEWORK
---
{homework_text[:14000]}"""
        raw = prompt_ollama(prompt, model=self.model, host=self.host, system=system)
        lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
        if not lines:
            return False, "Empty reviewer response"
        first = lines[0].upper()
        if first.startswith("PASS"):
            return True, ""
        detail = "\n".join(lines[1:]) if len(lines) > 1 else raw.strip()
        return False, detail[:2000]

    def generate_homework_until_validated(
        self,
        topic_summary: str,
        tier_counts: dict[str, int],
        question_specs: Optional[list[dict]] = None,
        levels: Optional[list[str]] = None,
        extra_system: Optional[str] = None,
        max_attempts: int = 4,
    ) -> tuple[str, str]:
        """
        Generate homework and run reviewer until PASS or max_attempts.
        Returns (homework_text, validation_note). Raises ValueError if never passes.
        """
        if not (topic_summary or "").strip():
            text = self.generate_differentiated_homework(
                topic_summary,
                tier_counts,
                question_specs=question_specs,
                levels=levels,
                extra_system=extra_system,
            )
            return text, "Skipped validation (no topic text)."
        specs = question_specs or [
            {"type": "MCQ", "count": 2},
            {"type": "Fill in the blanks", "count": 2},
            {"type": "Subjective questions", "count": 1},
        ]
        levels = levels or ["Extension", "Core", "Support"]
        feedback: Optional[str] = None
        last_fail = ""
        for attempt in range(max_attempts):
            text = self.generate_differentiated_homework(
                topic_summary,
                tier_counts,
                question_specs=specs,
                levels=levels,
                extra_system=extra_system,
                revision_feedback=feedback,
            )
            ok, reason = self.review_homework_completeness(text, levels, specs)
            if ok:
                return text, f"Homework passed validation (attempt {attempt + 1} of {max_attempts})."
            last_fail = reason
            feedback = (
                "Your previous homework was rejected by an automated reviewer.\n"
                f"Reviewer feedback: {reason}\n\n"
                "Regenerate the COMPLETE homework from scratch. "
                "Include every required section heading and, under each section, every required question type with the counts the teacher asked for."
            )
        raise ValueError(
            f"Homework did not pass validation after {max_attempts} attempts. Last reviewer note: {last_fail}"
        )

    def generate_quotes_for_badges(
        self,
        names: list[str],
        score_pcts: list[float],
        extra_system: Optional[str] = None,
    ) -> list[str]:
        """One short motivational quote per student; unique lines."""
        n = len(names)
        if n == 0:
            return []
        if n != len(score_pcts):
            score_pcts = list(score_pcts) + [0.0] * (n - len(score_pcts))

        system = (
            "You write short, sincere motivational one-liners for students. "
            "Each quote must be unique; do not repeat wording across students. "
            "Keep each under 22 words. Classroom-appropriate."
        )
        if extra_system and extra_system.strip():
            system = system + "\n\n" + extra_system.strip()
        roster = "\n".join(f"{i + 1}. {names[i]} — class score {score_pcts[i]:.1f}%")
        prompt = (
            f"Write exactly {n} numbered lines. Line format: number, period, space, then the quote only.\n"
            f"Each line is a different motivational quote for one student:\n\n{roster}\n\n"
            "Example line: 1. Your persistence is paying off—keep reaching higher!"
        )
        raw = prompt_ollama(prompt, model=self.model, host=self.host, system=system)
        return self._parse_numbered_quotes(raw, n)

    @staticmethod
    def _parse_numbered_quotes(raw: str, n: int) -> list[str]:
        out = [""] * n
        for line in raw.splitlines():
            line = line.strip()
            m = re.match(r"^(\d+)\.\s*(.+)$", line)
            if m:
                idx = int(m.group(1)) - 1
                if 0 <= idx < n:
                    out[idx] = m.group(2).strip()
        if all(out):
            return out
        return [FALLBACK_BADGE_QUOTES[i % len(FALLBACK_BADGE_QUOTES)] for i in range(n)]
