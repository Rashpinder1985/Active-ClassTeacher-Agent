"""Load and normalize poll responses from Excel; compute scores and tiers."""
from io import BytesIO
from typing import List, Optional, Tuple

import pandas as pd

from classroom_report.config import STUDENT_NAME_COLUMN


def _find_student_name_column(df: pd.DataFrame) -> str:
    """Find column that matches STUDENT_NAME_COLUMN (case-insensitive)."""
    for c in df.columns:
        if str(c).strip().lower() == STUDENT_NAME_COLUMN.lower():
            return c
    raise ValueError(
        f"Excel must have a column named '{STUDENT_NAME_COLUMN}'. "
        "Expected format: Student Name + Q1, Q2, ... or Student Name + Q1_Selected/Q1_Correct pairs."
    )


def _detect_selected_correct_pairs(df: pd.DataFrame, name_col: str) -> Optional[List[Tuple[str, str, str]]]:
    """
    If Excel has Qn_Selected and Qn_Correct columns, return list of (question_label, selected_col, correct_col).
    E.g. [("Q1", "Q1_Selected", "Q1_Correct"), ("Q2", "Q2_Selected", "Q2_Correct"), ...]
    Uses actual df column names for lookup.
    """
    col_map = {str(c).strip(): c for c in df.columns}
    cols = list(col_map.keys())
    selected = [c for c in cols if c.endswith("_Selected") or c.endswith("_selected")]
    if not selected:
        return None
    pairs = []
    for c in selected:
        base = c.replace("_Selected", "").replace("_selected", "")
        correct_name = base + "_Correct"
        correct_alt = base + "_correct"
        if correct_name in cols:
            pairs.append((base, col_map[c], col_map[correct_name]))
        elif correct_alt in cols:
            pairs.append((base, col_map[c], col_map[correct_alt]))
    if not pairs:
        return None
    return sorted(pairs, key=lambda x: x[0])


def _get_question_columns(df: pd.DataFrame, name_col: str) -> List[str]:
    """Return list of question columns (exclude name column and any non-question columns)."""
    exclude = {name_col}
    # Common question patterns: Q1, Q2, Question 1, etc.
    q_cols = []
    for c in df.columns:
        if c in exclude:
            continue
        if isinstance(c, str) and (c.strip().upper().startswith("Q") or "question" in c.strip().lower()):
            if "_Selected" not in c and "_Correct" not in c:
                q_cols.append(c)
        elif isinstance(c, (int, float)) or (isinstance(c, str) and c.strip().replace(".", "").isdigit()):
            q_cols.append(c)
    if not q_cols:
        # Fallback: all columns except name and Email ID / Selected / Correct
        q_cols = [
            c for c in df.columns
            if c not in exclude
            and "_Selected" not in str(c)
            and "_Correct" not in str(c)
        ]
    return q_cols


def load_responses(
    file_or_bytes: BytesIO | bytes | str,
    answer_key: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load Excel and return a normalized DataFrame: Student Name + Q1, Q2, ... with 1=correct, 0=incorrect.

    Supports two formats:
    1. Selected/Correct: columns like Q1_Selected, Q1_Correct (letters A/B/C/D). Score 1 where Selected == Correct.
    2. Wide: Student Name + Q1, Q2, ... with values 1/0 or A/B/C and optional answer_key (or first row as key).
    """
    df = pd.read_excel(file_or_bytes, engine="openpyxl")
    if df.empty or len(df) < 1:
        raise ValueError("Excel file is empty or has no data rows.")
    name_col = _find_student_name_column(df)

    # Format 1: Qn_Selected and Qn_Correct columns (e.g. Q1_Selected, Q1_Correct)
    pairs = _detect_selected_correct_pairs(df, name_col)
    if pairs:
        out = df[[name_col]].copy()
        out.columns = [STUDENT_NAME_COLUMN]
        for q_label, selected_col, correct_col in pairs:
            selected = df[selected_col].astype(str).str.strip().str.upper()
            correct = df[correct_col].astype(str).str.strip().str.upper()
            out[q_label] = (selected == correct).astype(int)
        return out

    # Format 2: wide format (Q1, Q2, ... with 1/0 or answer key)
    q_cols = _get_question_columns(df, name_col)
    if not q_cols:
        raise ValueError(
            "No question columns found. Use Q1, Q2, ... or Q1_Selected/Q1_Correct, Q2_Selected/Q2_Correct, etc."
        )

    # Optional: first row as answer key (if first cell is "key"/"answer" or user provided key)
    key_row = None
    if answer_key:
        key_parts = [x.strip() for x in answer_key.split(",")]
        if len(key_parts) >= len(q_cols):
            key_row = key_parts[: len(q_cols)]
        else:
            key_row = key_parts + [None] * (len(q_cols) - len(key_parts))
    else:
        first_cell = str(df.iloc[0].get(name_col, "")).strip().lower()
        if first_cell in ("key", "answer", "answers", ""):
            first = df.iloc[0]
            key_row = [first.get(c) for c in q_cols]
            df = df.iloc[1:].reset_index(drop=True)

    # Normalize to 0/1 (ensure numeric: Excel often gives "1.0"/"0.0" as strings)
    out = df[[name_col]].copy()
    out.columns = [STUDENT_NAME_COLUMN]
    for j, q in enumerate(q_cols):
        col = df[q].astype(str).str.strip().str.lower()
        if key_row is not None and j < len(key_row):
            correct_val = str(key_row[j]).strip().lower() if key_row[j] is not None else "1"
            out[q] = (col == correct_val).astype(int)
        else:
            # Assume 1 = correct, 0 = incorrect; map common values then coerce to numeric
            mapped = col.replace(
                {"1": 1, "1.0": 1, "yes": 1, "y": 1, "correct": 1, "true": 1, "0": 0, "0.0": 0, "no": 0, "n": 0, "false": 0, "": 0}
            )
            out[q] = pd.to_numeric(mapped, errors="coerce").fillna(0).clip(0, 1).astype(int)
    return out


def normalize_responses(
    df: pd.DataFrame,
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Ensure DataFrame has Student Name and question columns; return (df, question_columns).
    """
    name_col = _find_student_name_column(df)
    q_cols = _get_question_columns(df, name_col)
    return df[[name_col] + q_cols], q_cols
