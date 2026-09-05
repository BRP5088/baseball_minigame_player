# Obsolete — superseded, kept only because this project has no version control

Archived 2026-08-25 per QA_FINDINGS.md M1/M2. Nothing imports these.

- `hand_card_matcher.py` + `hand_card_embeddings.json` — CLIP-embedding hand
  card matcher. Superseded by `hand_digit_reader.py` (PaddleOCR). The cache was
  also built against the OLD hand crop geometry (y0=0.770), so it is stale as
  well as unused.
- `digit_recognizer.py` + `digit_templates/` — Hough-circle + template-matching
  digit recogniser. Rejected: it matched WRONG digits at score 1.000, making its
  confidence scores untrustworthy. See LOCAL_VISION_EXPERIMENTS.md §8.

Safe to delete outright once you're confident they aren't wanted.
