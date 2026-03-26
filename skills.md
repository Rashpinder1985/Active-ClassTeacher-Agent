# Skills

## Ingest

1. Accept lecture slides (`.pptx` or `.pdf`) and poll responses (`.xlsx`).
2. Parse slides for full text and poll-tagged slides (titles containing Poll/Question/Quiz).
3. Parse Excel: wide format (`Q1`, `Q2`, …) or Selected/Correct pairs (`Q1_Selected`, `Q1_Correct`).

## Analytics

1. Score students, assign tiers (Extension / Core / Support), compute top performers.
2. Build engagement charts from question columns.

## Reports

1. **Topic summary** — short class summary from slide content (optional poll context).
2. **Homework** — differentiated Extension / Core / Support; no student names in LLM prompts for homework (only topic + tier counts).

## Guardrails

- Homework prompts: include topic text and tier counts only — not student names.
- MCQ answers belong in a final Answer key section, not inline.
