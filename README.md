# Casino bonus scraper

Pulls the welcome bonus for 3 casinos from a public comparison article on RotoWire, uses Gemini to turn the free-text terms into structured fields, writes `data/casino.json`, and renders it as a static table in `docs/index.html` (served by GitHub Pages).

Live page: https://eddiemotloung.github.io/casino-bonus-scraper/

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

Exit code 0 on success, 1 with a `FAILED: [step] ...` message otherwise.

## Pipeline

| Step | File | Output | Fails when |
|---|---|---|---|
| 1. Fetch | `src/fetcher.py` | `data/raw_source.html` | robots.txt disallows, HTTP 401/403/429/503, CAPTCHA page, empty file |
| 2. Extract | `src/extractor.py` | `data/unstructured_cache.txt` | no article/table, fewer than 3 rows, empty file |
| 3. Structure (LLM) | `src/llm_wrapper.py` | `data/casino.json` | invalid JSON, wrong record count, missing fields, wagering or deposit number not present in the source text |
| 4. Render | `src/build_page.py` | `docs/index.html` | JSON fails validation, empty file |

Every step checks that its output exists and is non-empty before the next one runs.

Notes:
- The LLM output is cross-checked against the scraped text, so a hallucinated wagering multiplier or deposit stops the run instead of being published.
- On a 5xx (overload) Gemini is retried with backoff and then falls back to other Gemini models. 4xx errors skip to the next model.
- `source_url` is set by the scraper, not by the model. It is the article the data came from.
- The source lists US offers, so amounts are in USD.

## Output fields

`casino_name`, `welcome_bonus`, `wagering_requirement` (integer multiplier), `minimum_deposit`, `source_url`.
