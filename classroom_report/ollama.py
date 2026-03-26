"""Ollama HTTP client for topic summary and homework."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Optional

from classroom_report.config import OLLAMA_HOST, normalize_homework_levels

# Must stay aligned with the "Homework layout (always follow)" section in agent.md at repo root.
# Injected before full agent.md/skills.md so LangGraph / full pipeline runs always see these rules first.
HOMEWORK_LAYOUT_AGENT_RULES = """Homework layout (always follow — from agent.md):

When generating differentiated homework:

1. Levels (questions): Support → Core → Extension only (omit levels the teacher turned off). The app sorts them; you do too.
2. Inside each level: MCQs first, then fill in the blanks, then subjective — skip a block if its count is zero.
3. Counts: Match the teacher's numbers per level (MCQ / fill-in / subjective) exactly, not "roughly."
4. Answers: Put no correct MCQ answers next to questions. One final Answer key at the end, with subsections Support → Core → Extension.

A reviewer step in code checks this; if you drift, output is rejected and regenerated."""

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

    def route_next_post_analytics(
        self,
        *,
        allowed_ids: list[str],
        context_text: str,
        extra_system: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        LLM chooses the next graph node from a closed set. Returns (next_id, reason).
        Caller must validate next_id ∈ allowed_ids (or use fallback).
        """
        if not allowed_ids:
            return "end", "no allowed steps"
        if len(allowed_ids) == 1:
            return allowed_ids[0], "single option"

        allowed_str = ", ".join(allowed_ids)
        system = (
            "You are a routing controller for a teacher reporting pipeline after quiz analytics. "
            "Choose exactly ONE next step that best serves the teacher (e.g. summary before homework when both are needed). "
            f"The field 'next' MUST be exactly one of: {allowed_str}. "
            'Reply with a single JSON object only, no markdown: {"next":"<id>","reason":"<short reason>"}'
        )
        if extra_system and extra_system.strip():
            system = system + "\n\n" + extra_system.strip()
        prompt = (
            "Context (facts about the run):\n"
            f"{context_text}\n\n"
            f"Allowed next nodes: {allowed_str}\n"
            "Output JSON only."
        )
        raw = prompt_ollama(prompt, model=self.model, host=self.host, system=system)
        next_id, reason = self._parse_router_json(raw, allowed_ids)
        return next_id, reason

    @staticmethod
    def _parse_router_json(raw: str, allowed_ids: list[str]) -> tuple[str, str]:
        text = (raw or "").strip()
        if "{" in text and "}" in text:
            start = text.index("{")
            end = text.rindex("}") + 1
            try:
                data = json.loads(text[start:end])
                nxt = str(data.get("next", "")).strip()
                rsn = str(data.get("reason", "")).strip() or "model choice"
                if nxt in allowed_ids:
                    return nxt, rsn
            except (json.JSONDecodeError, ValueError, KeyError):
                pass
        return allowed_ids[0], "fallback (parse or invalid next)"

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
                "Support\n\n"
                "(Placeholder — generate homework from topic text.)\n\n"
                "Core\n\n(Placeholder.)\n\n"
                "Extension\n\n(Placeholder.)\n\n"
                "Answer key\n\n(MCQ answers listed here when generated.)"
            )
        specs = question_specs or [
            {"type": "MCQ", "count": 2},
            {"type": "Fill in the blanks", "count": 2},
            {"type": "Subjective questions", "count": 1},
        ]
        levels = normalize_homework_levels(levels)
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

        per_level_lines: list[str] = []
        if n_mcq > 0:
            per_level_lines.append(
                f"   - Under **Objective (MCQ)**, list exactly {n_mcq} MCQ(s), each with four labeled options (A, B, C, D). "
                "Do not mark the correct answer beside the question."
            )
        if n_fill > 0:
            per_level_lines.append(
                f"   - Under **Fill in the blanks**, list exactly {n_fill} sentence(s) with ____ for the blank."
            )
        if n_subj > 0:
            per_level_lines.append(
                f"   - Under **Subjective**, list exactly {n_subj} short-answer prompt(s)."
            )
        per_level_block = "\n".join(per_level_lines) if per_level_lines else "   (No question types selected.)"

        ak_order = " → ".join(levels)
        system = (
            "You are a helpful assistant for teachers. You generate concrete homework activities. "
            "Do not mention student names or performance tiers. "
            "Use only the level headings requested (Support, Core, Extension). "
            "Never put MCQ correct answers inside the question sections—only in the final Answer key. "
            "Follow the exact section order and sub-structure described in the user message."
        )
        system = system + "\n\n" + HOMEWORK_LAYOUT_AGENT_RULES
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
            "### REQUIRED STRUCTURE (strict)\n\n"
            "**Part 1 — Questions only** (do not put MCQ answers here)\n\n"
            f"Use these main headings **in this exact order** (include only these levels): {levels_text}.\n\n"
            "Under EACH level heading, use these **subheadings in this order** (skip a subheading if its count is 0):\n"
            f"{per_level_block}\n\n"
            "Difficulty: **Support** = simpler, scaffolded; **Core** = standard; **Extension** = stretch / enrichment.\n\n"
            "**Part 2 — Answer key (must be the LAST section)**\n\n"
            "After all level sections, add a single final section titled **Answer key** (or Answer Key).\n"
            "Inside the answer key, use **subsections in this order** (omit levels you did not generate):\n"
            f"{ak_order}\n\n"
            "Under each subsection (Support, Core, Extension), give:\n"
            "- MCQ: numbered correct letters (1. A, 2. B, …)\n"
            "- Fill in the blanks: the word or phrase that belongs in each blank\n"
            "- Subjective: brief bullet marking criteria or sample points (optional but helpful)\n\n"
            f"**Counts per level** (must match exactly for each included level): {spec_text}.\n\n"
            "Do not output anything before the first level heading. Do not add content after the Answer key section."
        )
        return prompt_ollama(prompt, model=self.model, host=self.host, system=system)

    def review_homework_completeness(
        self,
        homework_text: str,
        levels: list[str],
        question_specs: list[dict],
    ) -> tuple[bool, str]:
        """LLM check: counts, section order, answer-key order, and basic quality."""
        if not (homework_text or "").strip():
            return False, "Homework text is empty."
        levels = normalize_homework_levels(levels)
        spec_lines = "\n".join(
            f"- Exactly {int(s.get('count', 0))} × {s.get('type', '')} per included level (if count is 0, skip that type)."
            for s in question_specs
        )
        levels_line = ", ".join(levels)
        canonical = " → ".join(levels)
        system = (
            "You are a strict QA reviewer for teacher homework. "
            "Check counts, document order, answer-key order, and that questions are clear and on-topic. "
            "Respond with exactly two lines: line 1 PASS or FAIL; line 2 if FAIL a short reason, else OK.\n\n"
            + HOMEWORK_LAYOUT_AGENT_RULES
        )
        prompt = f"""Teacher required these levels in order (before Answer key): {canonical}

Per level, required counts (each type with count 0 is not required):
{spec_lines}

STRUCTURE (must pass):
- Main sections for questions appear in order: {levels_line} (Support before Core before Extension when multiple appear).
- Under each level, question types appear in order: Objective MCQ block, then Fill in the blanks, then Subjective (or clearly labeled equivalents).
- **Answer key** is the last section. Inside it, subsections follow: {canonical} (Support answers, then Core, then Extension).

COUNTS:
- For each level and each type with count > 0, the homework must include exactly that many items (not fewer).

QUALITY:
- MCQs have four options; fill-ins use ____; questions relate to the topic; wording is clear for students.

---
HOMEWORK
---
{homework_text[:16000]}"""
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
        levels = normalize_homework_levels(levels)
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
                "Follow order: Support → Core → Extension for question sections; under each level use MCQ block, then fill-ins, then subjective; "
                "then a final Answer key with subsections Support → Core → Extension. "
                "Match exact counts per level and type."
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
        roster = "\n".join(
            f"{i + 1}. {names[i]} — class score {score_pcts[i]:.1f}%" for i in range(n)
        )
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
