"""Excel poll / quiz response loading and flexible column detection."""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any, List, Optional, Tuple

import pandas as pd

from classroom_report.config import (
    IDENTIFIER_COLUMN_NAMES,
    IDENTIFIER_HEADER_SUBSTRINGS,
    MAX_MARKS_COLUMN_NAMES,
    STUDENT_NAME_COLUMN,
    TOTAL_MARKS_COLUMN_NAMES,
)


def _norm_header(s: Any) -> str:
    return str(s).strip().lower()


def _column_matches_one_of(name: Any, candidates: Tuple[str, ...]) -> bool:
    return _norm_header(name) in candidates


def find_identifier_column(df: pd.DataFrame) -> str:
    """
    Detect the student row label column: Name, Email, Roll No, Student ID, etc.
    Does not require the exact header 'Student Name'.
    """
    cols_lower = {str(c).strip().lower(): c for c in df.columns}
    for pat in IDENTIFIER_COLUMN_NAMES:
        if pat in cols_lower:
            return cols_lower[pat]
    for c in df.columns:
        n = str(c).strip().lower()
        for sub in IDENTIFIER_HEADER_SUBSTRINGS:
            if sub in n:
                return c
    for c in df.columns:
        if df[c].dtype == object or str(df[c].dtype) == "string":
            return c
    if len(df.columns) == 2:
        c0, c1 = df.columns[0], df.columns[1]
        t0 = pd.to_numeric(df[c0], errors="coerce").notna().mean()
        t1 = pd.to_numeric(df[c1], errors="coerce").notna().mean()
        if t0 < 0.35 and t1 > 0.65:
            return c0
        if t1 < 0.35 and t0 > 0.65:
            return c1
    raise ValueError(
        "Could not detect a student identifier column. Use a header such as Name, Email, Roll No, or Student ID."
    )


def find_student_name_column(df: pd.DataFrame) -> str:
    """Backward-compatible alias; returns the detected identifier column (always renamed to Student Name in outputs)."""
    return find_identifier_column(df)


def _is_denominator_header(name: Any) -> bool:
    n = _norm_header(name)
    return any(
        x in n
        for x in (
            "max mark",
            "full mark",
            "out of",
            "total possible",
            "maximum mark",
            "maximum score",
            "max score",
        )
    )


def _find_score_column(df: pd.DataFrame, id_col: str) -> Optional[str]:
    """
    Find the main marks/score column for ranking and charts.
    Uses header names first, then fuzzy keywords, then numeric heuristic.
    """
    for c in df.columns:
        if c == id_col or _is_denominator_header(c):
            continue
        if _column_matches_one_of(c, TOTAL_MARKS_COLUMN_NAMES):
            return c

    for c in df.columns:
        if c == id_col or _is_denominator_header(c):
            continue
        n = _norm_header(c)
        if any(s in n for s in ("mark", "score", "obtained", "point", "grade", "percent", "gpa", "cgpa")) or n in ("%", "pct"):
            return c

    others = [c for c in df.columns if c != id_col and not _is_denominator_header(c)]
    if len(others) == 1:
        ser = pd.to_numeric(df[others[0]], errors="coerce")
        if ser.notna().sum() >= max(1, len(df) // 2):
            return others[0]

    best_col = None
    best_std = -1.0
    for c in df.columns:
        if c == id_col or _is_denominator_header(c):
            continue
        ser = pd.to_numeric(df[c], errors="coerce")
        valid = int(ser.notna().sum())
        if valid < max(1, len(df) // 2):
            continue
        std = float(ser.std()) if valid > 1 else 0.0
        mx = float(ser.max())
        mn = float(ser.min())
        if mx <= 0 and mn >= 0:
            continue
        if std > best_std:
            best_std = std
            best_col = c
    return best_col


def _find_max_marks_column(df: pd.DataFrame, name_col: str, total_col: str) -> Optional[str]:
    for c in df.columns:
        if c in (name_col, total_col):
            continue
        if _column_matches_one_of(c, MAX_MARKS_COLUMN_NAMES):
            return c
    return None


def _is_likely_metadata_column(name: Any, id_col: str) -> bool:
    n = _norm_header(name)
    if not n:
        return True
    if str(name) == str(id_col):
        return False
    sub = ("comment", "remarks", "notes", "phone", "section", "class", "gender", "dob", "address")
    return any(x in n for x in sub)


def _detect_selected_correct_pairs(df: pd.DataFrame, name_col: str) -> Optional[List[Tuple[str, str, str]]]:
    col_map = {str(c).strip(): c for c in df.columns}
    cols = list(col_map.keys())
    selected = [c for c in cols if c.endswith("_Selected") or c.endswith("_selected")]
    if not selected:
        return None
    pairs = []
    for c in selected:
        base = c.replace("_Selected", "").replace("_selected", "")
        for correct_name in (base + "_Correct", base + "_correct"):
            if correct_name in cols:
                pairs.append((base, col_map[c], col_map[correct_name]))
                break
    if not pairs:
        return None
    return sorted(pairs, key=lambda x: x[0])


def _has_per_question_columns(df: pd.DataFrame, id_col: str) -> bool:
    if _detect_selected_correct_pairs(df, id_col):
        return True
    for c in df.columns:
        if c == id_col:
            continue
        s = str(c).strip()
        if re.match(r"^Q\d+", s, re.IGNORECASE) and "_Selected" not in s and "_Correct" not in s:
            return True
        if "question" in s.lower() and "_Selected" not in s and "_Correct" not in s:
            return True
    return False


def get_question_columns(df: pd.DataFrame, id_col: str) -> List[str]:
    exclude = {id_col}
    q_cols: List[Any] = []
    for c in df.columns:
        if c in exclude:
            continue
        if isinstance(c, str) and (c.strip().upper().startswith("Q") or "question" in c.strip().lower()):
            if "_Selected" not in c and "_Correct" not in c:
                q_cols.append(c)
        elif isinstance(c, (int, float)) or (isinstance(c, str) and c.strip().replace(".", "").isdigit()):
            q_cols.append(c)
    if not q_cols:
        q_cols = [
            c
            for c in df.columns
            if c not in exclude
            and "_Selected" not in str(c)
            and "_Correct" not in str(c)
            and not _is_likely_metadata_column(c, id_col)
        ]
    return q_cols


def load_responses(file_or_bytes: BytesIO | bytes | str, answer_key: Optional[str] = None) -> pd.DataFrame:
    df = pd.read_excel(file_or_bytes, engine="openpyxl")
    if df.empty or len(df) < 1:
        raise ValueError("Excel file is empty or has no data rows.")
    id_col = find_identifier_column(df)

    pairs = _detect_selected_correct_pairs(df, id_col)
    if pairs:
        out = df[[id_col]].copy()
        out.columns = [STUDENT_NAME_COLUMN]
        for q_label, selected_col, correct_col in pairs:
            selected = df[selected_col].astype(str).str.strip().str.upper()
            correct = df[correct_col].astype(str).str.strip().str.upper()
            out[q_label] = (selected == correct).astype(int)
        return out

    if not _has_per_question_columns(df, id_col):
        score_col = _find_score_column(df, id_col)
        if score_col is not None:
            marks = pd.to_numeric(df[score_col], errors="coerce")
            max_col = _find_max_marks_column(df, id_col, score_col)
            if max_col is not None:
                denom = pd.to_numeric(df[max_col], errors="coerce")
                ratio = marks / denom.replace(0, float("nan"))
            else:
                max_m = float(marks.max())
                if max_m <= 0 or pd.isna(max_m):
                    raise ValueError("Score column has no positive values; check your marks/score data or add a Max Marks column.")
                ratio = marks / max_m
            ratio = pd.to_numeric(ratio, errors="coerce").clip(0, 1)
            out = df[[id_col]].copy()
            out.columns = [STUDENT_NAME_COLUMN]
            out["Q1"] = ratio
            return out

    q_cols = get_question_columns(df, id_col)
    if not q_cols:
        raise ValueError(
            "No question columns or score column found. Add Q1, Q2, …; Q1_Selected/Q1_Correct; "
            "or one column with marks/score (e.g. Total Marks, Score, Percentage) beside Name/Email/Roll."
        )

    key_row = None
    if answer_key:
        key_parts = [x.strip() for x in answer_key.split(",")]
        key_row = key_parts[: len(q_cols)] if len(key_parts) >= len(q_cols) else key_parts + [None] * (len(q_cols) - len(key_parts))
    else:
        first_cell = str(df.iloc[0].get(id_col, "")).strip().lower()
        if first_cell in ("key", "answer", "answers", ""):
            first = df.iloc[0]
            key_row = [first.get(c) for c in q_cols]
            df = df.iloc[1:].reset_index(drop=True)

    out = df[[id_col]].copy()
    out.columns = [STUDENT_NAME_COLUMN]
    yes_no = {"1": 1, "1.0": 1, "yes": 1, "y": 1, "correct": 1, "true": 1, "0": 0, "0.0": 0, "no": 0, "n": 0, "false": 0, "": 0}
    for j, q in enumerate(q_cols):
        col = df[q].astype(str).str.strip().str.lower()
        if key_row is not None and j < len(key_row):
            correct_val = str(key_row[j]).strip().lower() if key_row[j] is not None else "1"
            out[q] = (col == correct_val).astype(int)
        else:
            mapped = col.replace(yes_no)
            out[q] = pd.to_numeric(mapped, errors="coerce").fillna(0).clip(0, 1).astype(int)
    return out


def normalize_responses(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    id_col = find_identifier_column(df)
    q_cols = get_question_columns(df, id_col)
    return df[[id_col] + q_cols], q_cols
