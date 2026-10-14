# AIBoost Project Casino: casino bonus scraper

Pulls the welcome bonus for 3 casinos from a public comparison article on RotoWire, uses Gemini to turn the free-text terms into structured fields, writes `data/casino.json`, and renders it as a table in `docs/index.html` (served by GitHub Pages).

Live page: https://eddiemotloung.github.io/aiboost-project-casino/

## Install

Requires Python 3.10+.

```bash
pip install -r requirements.txt
cp .env.example .env      # then put your Gemini API key in .env
```

`.env` is gitignored. The key is read from `LLM_API_KEY` (or `GEMINI_API_KEY`) and never hard-coded.

## Run

```bash
python run.py
```

Exit code 0 when the review passes, 1 otherwise. Each run writes `runs/<run_id>/checklist.md` (a ledger of what was done), `ledger.json` and one log per step.

## Tests

```bash
python -m pytest -v
```

26 offline tests, one per requirement in the brief (no network or API key needed). See [REQUIREMENTS_CHECKLIST.md](REQUIREMENTS_CHECKLIST.md) for the requirement → test mapping.

## Pipeline

| Step | File | Output | Fails when |
|---|---|---|---|
| 1. Fetch | `src/fetcher.py` | `data/raw_source.html` | robots.txt disallows, HTTP 401/403/429/503, CAPTCHA page, empty file |
| 2. Extract | `src/extractor.py` | `data/unstructured_cache.txt` | no article/table, fewer than 3 rows, empty file |
| 3. Structure (LLM) | `src/llm_wrapper.py` | `data/casino.json` | fewer than 2 models answer, models disagree on wagering or deposit, a number isn't in the source text, invalid JSON, missing fields |
| 4. Render | `src/build_page.py` | `docs/index.html`, `docs/casino.json` | JSON fails validation, empty file |
| Review | `src/review.py` | — | any step not ticked, any artifact or log missing or empty, a casino in the JSON missing from the page |

How failures are handled:

- **Checklist ledger.** A step is only ticked once its output files and its log exist and are non-empty. A step that says it worked but wrote nothing doesn't count.
- **Review and retry.** After the run, `review.py` re-checks the ledger against what's on disk. If something failed, the pipeline is re-run from that step once, then the run fails with the reason written to `checklist.md`.
- **Two-model cross-check.** Two different Gemini models extract the terms independently. Wagering and minimum deposit must match between them and appear in the scraped text, otherwise nothing is published. If the bonus wording differs between the models, the run notes it in the log but still passes.
- **Overload handling.** 5xx responses are retried with backoff, then the next model in the fallback list is tried.

`source_url` is set by the scraper, not the model. The source covers US offers, so amounts are in USD.

## Output fields

`casino_name`, `welcome_bonus`, `wagering_requirement` (integer multiplier), `minimum_deposit`, `source_url`, plus `models_agree_on_bonus`. Top-level fields: `scraped_at`, `source_url`, `models`.
