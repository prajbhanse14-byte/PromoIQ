# PromoIQ Phase 5.2 — Dramatic Evidence Selection

## What changed
- Hook evidence is selected from the opening 8 seconds (or first 25% of the candidate), rather than only the first 3 seconds.
- Cliffhanger evidence is selected from the final 12 seconds (or final 40% of the candidate), rather than automatically taking the last editorial block.
- Within each search window, deterministic screenplay-text signals choose the strongest eligible beat. Ties prefer beats closer to the relevant clip edge.
- Both LLM-assisted and heuristic fallback candidates now use the selected source screenplay evidence for scoring.
- Evidence Inspector now shows selected timestamps, search windows, and the selection method.
- Added a regression test demonstrating that a dramatic warning can be selected over a generic action beat.

## Important limitation
This is still rule-based analysis of screenplay text. It cannot verify visual impact, acting, audio, edit continuity, or audience retention. Scores are ranking signals for human review, not probabilities of promo success.

## Installation
Replace the files in your existing project with the matching files from this package. Preserve your `.env` and confidential `input_data/` folder. Do not upload screenplay files or API keys to a public repository.

Run:
```bash
python -m pytest -q
streamlit run app.py
```

The two full-pack tests require the confidential 50-episode `input_data/` folder and are expected to be skipped or fail in this portable package if that folder is absent.
