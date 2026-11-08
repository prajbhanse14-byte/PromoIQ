# PromoIQ — Screenplay-to-Promo Discovery

PromoIQ is a Python-based application that analyses timestamped screenplay text and identifies promising short promotional clip windows. It helps an editor discover moments with a strong opening hook, dramatic tension, and an ending that encourages the audience to keep watching.

The project includes a Streamlit interface, a screenplay parser, candidate-generation and ranking logic, batch processing for multiple episodes, and CSV/JSON reports. An optional Groq-powered language-model path is also integrated, with a deterministic heuristic fallback when an API call is unavailable or fails.

## 1. Problem Statement

Finding promotional moments in long screenplays can require manually reviewing many scenes and dialogue exchanges. This is time-consuming and can make it difficult to consistently identify short sequences that work as standalone promotional clips.

PromoIQ addresses this by parsing timestamped screenplay blocks, generating candidate clip windows, evaluating their dramatic and contextual qualities, and ranking the resulting suggestions.

## 2. Objectives

- Parse timestamped screenplay text into structured blocks.
- Identify potential promotional windows between 20 and 60 seconds.
- Evaluate candidate moments for hooks, cliffhangers, standalone clarity, and duration suitability.
- Rank candidates to help editors prioritise promising clips.
- Process a collection of episode scripts in batch mode.
- Export candidate details and run summaries for further review.
- Provide a browser-based interface through Streamlit.

## 3. Key Features

- **Screenplay parsing:** Extracts timestamped content and associated screenplay information from text files.
- **Candidate generation:** Finds potential clip windows from the parsed screenplay blocks.
- **Hook analysis:** Looks for dramatic stakes, urgency, confrontation, mystery, and other attention-grabbing moments.
- **Cliffhanger analysis:** Rewards unresolved threats, open questions, conditions, and suspense, while accounting for resolved moments.
- **Standalone clarity:** Estimates whether a candidate contains enough context to make sense as an independent promotional clip.
- **Duration scoring:** Checks the 20–60 second requirement and favours durations around the target length.
- **Candidate ranking:** Combines the scoring factors to produce an ordered shortlist.
- **Batch processing:** Runs the analysis across multiple episode text files.
- **Export:** Produces CSV, JSON, and text reports.
- **Optional LLM support:** Can request candidate suggestions from Groq using the OpenAI-compatible API. If the request fails, the engine falls back to heuristic candidate generation.

## 4. Technology Stack

- **Language:** Python
- **User interface:** Streamlit
- **Data handling and reports:** Python standard library and CSV/JSON
- **LLM integration:** OpenAI Python SDK connected to Groq's OpenAI-compatible API
- **Model configured for the project:** `openai/gpt-oss-20b`
- **Testing:** pytest

## 5. Project Structure

```text
PromoIQ/
├── app.py                         # Streamlit application
├── run_all_episodes.py             # Batch processing entry point
├── requirements.txt                # Python dependencies
├── .env.example                    # Example environment configuration
├── input_data/                     # Episode screenplay .txt files
├── outputs/                        # Generated reports and candidate exports
├── promoiq/
│   ├── parser.py                   # Timestamped screenplay parsing
│   ├── engine.py                   # Candidate generation and orchestration
│   └── scoring.py                  # Candidate quality scoring
└── tests/
    ├── test_parser.py              # Parser tests
    └── test_scoring_quality.py     # Scoring behaviour tests
```

## 6. Setup and Installation

### Prerequisites

- Python installed on your system
- A terminal or command prompt
- Internet access if using the optional Groq integration

### Create and activate a virtual environment

From the project root directory:

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell, activate it with:

```powershell
.venv\Scripts\Activate.ps1
```

### Install dependencies

```bash
pip install -r requirements.txt
```

The Groq integration uses the OpenAI Python SDK. If it is not already installed by the requirements file, install it with:

```bash
pip install openai
```

## 7. Configuration for Optional Groq Integration

The heuristic workflow can be used without an API key. To enable the optional Groq model path:

1. Copy the example configuration file:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and provide your Groq API key and model:

   ```env
   GROQ_API_KEY=your_groq_api_key
   GROQ_MODEL=openai/gpt-oss-20b
   ```

3. Load the variables into the current terminal session on macOS/Linux:

   ```bash
   set -a
   source .env
   set +a
   ```

Keep `.env` private. Do not commit it or include it in a submission archive. Submit `.env.example` instead, with no real API key.

When an LLM request succeeds, the engine marks the generated candidate method as `llm_plus_rules`. If the API request fails or the model output cannot be used, the engine falls back to heuristic generation. The API key, model availability, account limits, and network connection can affect LLM execution.

## 8. Running the Application

Activate the virtual environment, navigate to the project root, and run:

```bash
streamlit run app.py
```

Streamlit prints a local address in the terminal, commonly:

```text
http://localhost:8501
```

Open that address in a web browser to use the PromoIQ interface. Keep the terminal process running while using the application. Stop the local server with `Ctrl + C`.

## 9. Running Batch Analysis

Place one timestamped episode screenplay text file per episode in `input_data/`. Then, from the project root with the virtual environment activated, run:

```bash
python run_all_episodes.py
```

The batch runner processes the `.txt` files in `input_data/` and writes the generated reports to `outputs/`. The batch runner is configured to request LLM-based candidates; episodes may use heuristic fallback when an LLM request fails.

## 10. Generated Outputs

The batch workflow generates the following files in `outputs/`:

| File | Description |
|---|---|
| `PromoIQ_parserfix_ranked_candidates.csv` | Ranked candidate clips with timestamps, duration, scores, hook, cliffhanger, and generation method. |
| `PromoIQ_parserfix_full_run.json` | Detailed per-episode analysis results, including statuses and candidate data. |
| `PromoIQ_parserfix_episode_report.csv` | Episode-level processing summary. |
| `PromoIQ_parserfix_run_report.txt` | Human-readable summary of the batch run. |

The CSV can be opened in spreadsheet software for filtering and review. The JSON file contains more detailed structured output for programmatic use.

## 11. Scoring Overview

PromoIQ uses multiple factors to assess candidate quality:

| Scoring factor | Purpose |
|---|---|
| Hook score | Estimates how strongly the opening captures attention through stakes, urgency, confrontation, or mystery. |
| Cliffhanger score | Estimates how effectively the ending leaves tension, an unresolved question, a threat, or an open loop. |
| Standalone score | Estimates whether the clip contains sufficient context to be understood independently. |
| Duration score | Evaluates suitability within the 20–60 second target and favours a duration around 40 seconds. |

The factors are combined into a total score used to rank candidate windows. Scores are decision-support signals, not a guarantee that a clip will perform well with an audience.

## 12. Recorded Baseline Results

The completed deterministic batch run on the supplied screenplay collection produced the following results:

| Metric | Result |
|---|---:|
| Episode scripts processed | 50 |
| Episodes with candidates | 50 / 50 |
| Scenes detected | 100 |
| Timestamped screenplay blocks parsed | 3,727 |
| Candidate clips generated | 161 |
| Candidates within 20–60 seconds | 161 / 161 |
| Candidate score range | 34.6–70.2 |
| Mean candidate score | 42.2 |

The 161-candidate baseline above was produced by the deterministic heuristic workflow. The Groq path was separately tested on an individual episode and successfully returned one accepted 34-second candidate. A complete 50-episode Groq-generated batch has not been independently verified; therefore, the baseline figures should not be described as LLM-generated results.

## 13. Running Tests

From the project root, with the virtual environment activated:

```bash
python -m pytest -q
```

This runs the parser and scoring test suite.

## 14. Limitations and Future Improvements

- PromoIQ analyses screenplay text and timestamps; it does not analyse the corresponding video footage.
- Suggested time windows must be checked against the actual video for visual continuity, shot changes, audio synchronisation, pacing, and edit points.
- A candidate may require editorial context that is not fully represented in the screenplay text.
- Heuristic scores are approximate indicators and do not replace human editorial judgement or audience testing.
- LLM generation depends on external API availability, model access, request limits, and valid model output. The heuristic fallback is used when LLM generation cannot be completed.

Potential future improvements include video-aware validation, more robust scene-boundary handling, editor feedback for score calibration, and systematic evaluation of LLM-generated candidates across the full episode collection.

## 15. Conclusion

PromoIQ provides an end-to-end prototype for discovering and ranking short promotional moments from timestamped screenplay text. It combines structured parsing, rule-based candidate scoring, batch reporting, and an optional language-model integration in a Streamlit application. The generated clips are intended as editorial suggestions that should be reviewed against the original video before final use.

## Optional multi-segment edit plans

Each continuous candidate may also include an optional two-segment edit suggestion. The current prototype proposes retaining the opening 40% and closing 40% of the candidate window, omitting the middle 20%. The two segments remain in chronological order and their combined runtime is checked against the 20–60 second requirement. This is a deterministic edit-plan heuristic, not an automatically rendered video or a guarantee of narrative continuity. Every plan is flagged for human editorial review.

The Streamlit interface displays the optional segment timestamps, and the CSV export includes the explanation, standalone context, quality tier, review flags, and serialized edit plan.

## Validation update

The latest local regression run processed 50 screenplay files, parsed 3,727 timed blocks, and generated 161 heuristic candidates; all 161 continuous candidates met the 20–60 second constraint. The optional two-segment plan was available for 155 of the 161 candidates. The automated test suite passed 15 tests. In this run, all 50 episodes used the heuristic path; this is not evidence of a successful full-batch LLM run.


## Candidate quality evaluation (Phase 3)

PromoIQ now performs transparent rule-based quality triage after ranking. It flags weak
hook/cliffhanger/standalone scores, low overall scores, missing explanations/context,
duration violations, and substantial overlap between candidates from the same episode.
Multi-segment continuity warnings are carried into the candidate review flags.

The Streamlit app displays the quality summary and provides downloadable quality-review
JSON and CSV files. These flags are review priorities, not ground-truth judgements or
measured editorial accuracy. Human reviewers must still watch the corresponding video.


## Ranking improvements (Phase 4)

The scoring model now uses five transparent signals:
- Hook strength: 30%
- Cliffhanger strength: 30%
- Standalone clarity: 25%
- Duration fit: 10%
- Evidence completeness: 5%

The final ranking uses total score, then hook, cliffhanger and standalone scores
as tie-breakers. Evidence completeness rewards sufficient screenplay text,
speaker attribution, basic causal/contrast connectors, and distinct opening
and closing evidence. Additional cliffhanger patterns cover identity reveals,
hidden people, and truth-reveal setups.

These are deterministic screenplay-text heuristics. They do not evaluate acting,
visual composition, soundtrack, editing rhythm, or audience retention. The
score must not be interpreted as a measured probability of promo success.


## Source-grounded scoring (Phase 5)

LLM-generated hook/cliffhanger descriptions are now kept separate from score inputs.
The score is calculated from actual timestamped screenplay evidence: the opening
editorial beat in the first three seconds and the final editorial beat near the cut.
Warning/imperative language (for example, "turn around", "look for yourself",
"watch out", or "leave now") is recognized as one possible cliffhanger signal.

This is still a text heuristic. A command may be ordinary dialogue rather than a
meaningful suspense beat, so editor review remains necessary.
