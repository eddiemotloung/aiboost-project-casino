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
| 2. Extract | `src/extractor.py` | `data/unstructured_cache.txt` | RotoWire extractor: no article/table or fewer than 3 rows. Generic: under 200 chars of text. Either: empty file |
| 3. Structure (LLM) | `src/llm_wrapper.py` | `data/casino.json` | fewer than 2 models answer, models pick different casinos or disagree on wagering or deposit, a number isn't in the source text, invalid JSON, missing fields |
| 4. Render | `src/build_page.py` | `docs/index.html`, `docs/casino.json` | JSON fails validation, empty file |
| Review | `src/review.py` | — | any step not ticked, any artifact or log missing or empty, a casino in the JSON missing from the page |

How failures are handled:

- **Checklist ledger.** A step is only ticked once its output files and its log exist and are non-empty. A step that says it worked but wrote nothing doesn't count.
- **Review and retry.** After the run, `review.py` re-checks the ledger against what's on disk. If something failed, the pipeline is re-run from that step once, then the run fails with the reason written to `checklist.md`.
- **Two-model cross-check.** Two different Gemini models extract the terms independently. Wagering and minimum deposit must match between them and appear in the scraped text, otherwise nothing is published. If the bonus wording differs between the models, the run notes it in the log but still passes.
- **Overload and rate limits.** 503 (overloaded) and 429 (rate limited) responses are retried with a wait, then the next model in the fallback list is tried.

`source_url` is set by the scraper, not the model. The source covers US offers, so amounts are in USD.

## Adding a source

Extractors are pluggable, one per domain, in `src/extractor.py`:

```python
@register("example.com")
def example(html, url):
    # return one {"kind": "row", "casino": ..., "source_url": url, "text": ...} per casino
```

- **Site-specific extractor.** `rotowire.com` is the only one registered. It reads the bonus table, one row per casino, which gives the LLM small, focused blocks.
- **Generic fallback.** Any domain without an extractor gets the page's main text with navigation, scripts and footers removed. The LLM finds the first 3 casinos that state a wagering requirement and a minimum deposit. The same checks apply: two models must pick the same casinos and agree on the numbers, and the numbers must appear in the page text. Because they only have to appear somewhere on the page, this check is looser than with a dedicated extractor.
- **Forcing an extractor.** `EXTRACTOR=generic python run.py` uses the generic path on any URL.

So a new source is one small function, or nothing at all if the generic path is good enough for that site. Fetching, the LLM step, checks, ledger and page don't change.

> **Review note:** the first version had the extractor hard-wired to RotoWire's layout, with no way to add a second source. @eddiemotloung caught this during review ("can this be used for multiple articles or sources?"), and the pluggable extractors and generic fallback were added in response.

## Output fields

`casino_name`, `welcome_bonus`, `wagering_requirement` (integer multiplier), `minimum_deposit`, `source_url`, plus `models_agree_on_bonus`. Top-level fields: `scraped_at`, `source_url`, `extractor`, `models`.

## Testing

Tested on 14 October 2026. **Result: 35/35 automated tests passed, and a live end-to-end run passed review.**

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
| Source plugins | RotoWire URLs (incl. subdomains) use the RotoWire extractor; unknown domains fall back to generic, with no false suffix match | 2 |
| Forcing an extractor | `EXTRACTOR=generic` forces the generic path; an unknown name is rejected | 1 |
| Adding a source | Registering one function for a new domain is all it takes | 1 |
| Generic extractor | Keeps the content, drops scripts, nav and footer; an empty page is rejected | 2 |
| Generic end to end | Generic text from the real saved page goes through the LLM step and gives the same 3 casinos | 1 |
| Same casino | Two models picking different casinos for a record stops the run | 1 |
| Rate limit | A 429 is waited out and retried, not skipped | 1 |

### Live end-to-end runs

`python run.py` was run for real against RotoWire and Gemini. The latest run is `20261014T170520Z`:

- **Fetch:** robots.txt allowed the page, and 341,578 bytes were saved.
- **Extract:** the RotoWire extractor found 3 casinos (BetMGM, Caesars Palace, bet365).
- **Structure:** gemini-3.5-flash-lite and gemini-flash-latest agreed on all wagering and deposit values. Earlier models in the list were rate limited, so the fallback was used.
- **Render and review:** the page was built, all 4 checklist steps were ticked, and the review passed.

An earlier run (`20261014T161032Z`, gemini-3.7-flash + gemini-3.5-flash-lite) gave the same numbers.

The output was checked by hand against the source table:

| Casino | Welcome bonus | Wagering | Min. deposit |
|---|---|---|---|
| BetMGM Casino | 100% up to 1,000 USD + 25 USD free | 15x | 10 USD |
| Caesars Palace Casino | 100% up to 1,000 USD | 15x | 20 USD |
| bet365 Casino | 100% up to 1,000 USD + 1,000 bonus spins | 20x | 10 USD |

### Generic extractor, live

`EXTRACTOR=generic python run.py` was run against the same page with real Gemini (run `20261014T170352Z`). **The review passed.**

- **Extract:** the generic path gave the LLM 8,505 chars of cleaned page text instead of the table rows.
- **Structure:** gemini-3.5-flash-lite and gemini-3.1-flash-lite independently found the **same 3 casinos with the same numbers** as the RotoWire extractor: wagering 15, 15, 20 and minimum deposits 10, 20, 10 USD. All values were in the page text.
- **What this shows:** a site with no dedicated extractor can still be scraped, with the same checks.

### Failure handling, live

- **Layout change:** pointed at a page with no bonus table, the pipeline retried once, exited with code 1, and wrote the reason to the checklist.
- **Rate limits:** when only one Gemini model was available (the others returned 429 or 503), the two-model run **failed safely**. Nothing was published, the checklist recorded why, and the live page kept the last good data.
- **Wording slip:** in a single-model check, one model wrote "1,000 USD bonus spins". This is why bonus wording isn't treated as verified (see `models_agree_on_bonus`).
