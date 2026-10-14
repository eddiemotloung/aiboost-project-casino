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

## Testing

Tested on 14 October 2026. **Result: 26/26 automated tests passed, and a live end-to-end run passed review.**

Run the tests yourself:

```bash
python -m pytest -v
```

They run offline (no internet or API key needed): the Gemini client is replaced by a fake one, so the tests check how the pipeline handles model output. The real committed files in `data/` are checked as evidence. [REQUIREMENTS_CHECKLIST.md](REQUIREMENTS_CHECKLIST.md) maps each line of the brief to its test.

### What was tested

| Area | What is checked | Tests |
|---|---|---|
| Source | Exactly 3 casinos are pulled, all from the same RotoWire page | 1 |
| Layout change | A page without the bonus table fails with a clear error | 1 |
| robots.txt | If robots.txt disallows the page, it is never requested | 1 |
| Blocks | HTTP 401, 403, 429 and 503 stop the run; nothing tries to get around them | 4 |
| CAPTCHA | A CAPTCHA page stops the run | 1 |
| Honest scraper | Requests use an identifying bot User-Agent, not a fake browser | 1 |
| LLM step | The scraped free text is what Gemini receives, and the JSON is built from its answer | 1 |
| Hallucination | A wagering value the model invents (e.g. 35x, not in the source) is rejected and nothing is written | 1 |
| Model agreement | Two models disagreeing on the minimum deposit stops the run | 1 |
| Overload | A model returning 503 is retried, then the next model is used | 1 |
| API key | A missing key gives a clear error | 1 |
| JSON fields | `casino.json` has 3 casinos with welcome bonus, integer wagering, deposit with currency, and source URL | 1 |
| Bad JSON | Invalid JSON or the wrong number of casinos is rejected | 1 |
| Not hand-typed | Every number in `casino.json` is traced back to the saved source page | 1 |
| Empty output | A missing or 0-byte output file stops the run | 1 |
| Web page | The page is a 3-row table built from `casino.json` | 1 |
| Phone | Viewport tag and a stacked-card layout on small screens | 1 |
| Page safety | Scraped text is HTML-escaped (no script injection) | 1 |
| Published files | `docs/index.html` and `docs/casino.json` match `data/casino.json` | 1 |
| Single command | `python run.py` runs all 4 steps, ticks the checklist and writes a log per step | 1 |
| Retry | A failed step is retried once, then reported in the checklist | 1 |
| Silent failure | A step that reports success but writes an empty file still fails | 1 |
| Secrets | `.env` and the API key are not committed | 1 |

### Live end-to-end run

`python run.py` was also run for real against RotoWire and Gemini (run `20261014T161032Z`):

- **Fetch:** robots.txt allowed the page, and 341,579 bytes were saved.
- **Extract:** 3 casinos found (BetMGM, Caesars Palace, bet365).
- **Structure:** gemini-3.8-flash was rate limited (HTTP 429), so the fallback was used. gemini-3.7-flash and gemini-3.5-flash-lite agreed on all wagering and deposit values.
- **Render and review:** the page was built, all 4 checklist steps were ticked, and the review passed.

The output was checked by hand against the source table:

| Casino | Welcome bonus | Wagering | Min. deposit |
|---|---|---|---|
| BetMGM Casino | 100% up to 1,000 USD + 25 on the house | 15x | 10 USD |
| Caesars Palace Casino | 100% up to 1,000 USD | 15x | 20 USD |
| bet365 Casino | 100% up to 1,000 USD + 1,000 bonus spins | 20x | 10 USD |

A failure run was also tested live: pointed at a page with no bonus table, the pipeline retried once, exited with code 1, and wrote the reason to the checklist.
