# AIBoost Project Casino

Look, here's the thing about casino bonuses. Every site screams "100% up to $1,000!" and then hides the parts that matter, the wagering and the minimum deposit, deep in the fine print.

So this project does one job, and does it right. It goes to a public RotoWire comparison article, pulls the welcome bonus for 3 casinos, has Gemini turn the messy terms into clean fields, writes them to `data/casino.json`, and puts them on a page you can read on your phone.

One command. No hand-typed data. No silent failures.

**See it live:** https://eddiemotloung.github.io/aiboost-project-casino/

## Get it running in 2 minutes

You need Python 3.10 or newer. That's it.

```bash
pip install -r requirements.txt
cp .env.example .env      # then put your Gemini API key in .env
git config core.hooksPath .githooks   # turns on the API-key guard (see below)
```

Your key lives in `.env`. That file is gitignored, so it never gets pushed. The code reads it from `LLM_API_KEY` (or `GEMINI_API_KEY`) and never hard-codes it.

And here's the part most people skip. Bots scan GitHub around the clock for leaked keys. So there's a guard: the pre-commit hook in `.githooks/` refuses any commit that contains a `.env` file or anything that looks like an API key. Tested it with a real key. It got blocked.

## Run it

```bash
python run.py
```

That's the whole thing. Exit code 0 means the review passed. Exit code 1 means something broke, and it tells you exactly what.

Every run leaves a paper trail in `runs/<run_id>/`: a `checklist.md` showing what got done, a `ledger.json`, and one log per step. So you never have to guess what happened.

## How it works: 4 steps and a review

| Step | File | Output | Stops the run when |
|---|---|---|---|
| 1. Fetch | `src/fetcher.py` | `data/raw_source.html` | robots.txt says no, the site blocks us (HTTP 401/403/429/503), a CAPTCHA shows up, or the file is empty |
| 2. Extract | `src/extractor.py` | `data/unstructured_cache.txt` | RotoWire extractor: no article/table, or fewer than 3 rows. Generic: under 200 chars of text. Either: empty file |
| 3. Structure (LLM) | `src/llm_wrapper.py` | `data/casino.json` | fewer than 2 models answer, models pick different casinos or disagree on wagering or deposit, a number isn't in the source text, invalid JSON, missing fields |
| 4. Render | `src/build_page.py` | `docs/index.html`, `docs/casino.json` | the JSON fails validation, or the file is empty |
| Review | `src/review.py` | — | any step not ticked, any file or log missing or empty, a casino in the JSON missing from the page |

Now let's talk about why you can trust what ends up on that page.

- **A step doesn't count until it proves it.** It only gets ticked once its output files and its log actually exist and aren't empty. A step that says "done!" and writes nothing? Doesn't count.
- **Then everything gets checked again.** After the run, `review.py` re-checks the checklist against what's actually on disk. If something failed, it re-runs from that step once. Still broken? The run fails, and the reason is written down in `checklist.md`.
- **Two AIs have to agree.** Two different Gemini models read the terms separately. The wagering and the minimum deposit have to match between them, and both numbers have to appear in the scraped text. If either check fails, nothing gets published. Period. If the models word the bonus differently, that gets noted in the log, but it doesn't block the run.
- **Overloads and rate limits get handled.** When Gemini is overloaded (503) or rate limited (429), the script waits, retries, and then moves on to the next model.

`source_url` is set by the scraper, never by the AI. The source covers US offers, so amounts are in USD.

## Adding a new source: one small function

Each website gets its own extractor, plugged in by domain in `src/extractor.py`:

```python
@register("example.com")
def example(html, url):
    # return one {"kind": "row", "casino": ..., "source_url": url, "text": ...} per casino
```

- **Site-specific extractor.** `rotowire.com` is the only one registered right now. It reads the bonus table one row per casino, so the AI gets small, focused blocks to work with.
- **Generic fallback.** Any site without its own extractor still works. The page gets stripped down to its main text (no menus, scripts or footers), and the AI finds the first 3 casinos that list both a wagering requirement and a minimum deposit. The same checks apply: two models, same casinos, same numbers, and the numbers have to be on the page. To be upfront: this check is looser, because a number only has to appear somewhere on the page, not in that casino's own row.
- **Want the generic path on purpose?** Run `EXTRACTOR=generic python run.py`.

So adding a new site is one small function, or nothing at all if the generic path handles it. Fetching, the AI step, the checks, the checklist and the page stay exactly the same.

> **Review note:** the first version had the extractor hard-wired to RotoWire's layout, with no way to plug in a second source. @eddiemotloung caught this during review ("can this be used for multiple articles or sources?"), and that's why the pluggable extractors and the generic fallback exist.

## What's in the JSON

Per casino: `casino_name`, `welcome_bonus`, `wagering_requirement` (a whole-number multiplier), `minimum_deposit`, `source_url`, plus `models_agree_on_bonus`.

At the top level: `scraped_at`, `source_url`, `extractor`, `models`.

## Testing: proof, not promises

Tested on 14 October 2026. **Result: 35 out of 35 automated tests passed, and the live end-to-end runs passed review.**

Don't take my word for it. Run them yourself:

```bash
python -m pytest -v
```

They run offline, with no internet or API key needed. The Gemini client is swapped for a fake one, so the tests check exactly how the pipeline handles what the AI sends back. The real files committed in `data/` are checked as evidence too. And [REQUIREMENTS_CHECKLIST.md](REQUIREMENTS_CHECKLIST.md) maps every single line of the brief to the test that proves it.

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

Tests are great. But this is the real deal: `python run.py` against the real RotoWire page and real Gemini. The latest run is `20261014T170520Z`:

- **Fetch:** robots.txt said yes, and 341,578 bytes came back.
- **Extract:** the RotoWire extractor found 3 casinos: BetMGM, Caesars Palace and bet365.
- **Structure:** gemini-3.5-flash-lite and gemini-flash-latest agreed on every wagering and deposit value. The models higher up the list were rate limited, so the fallback kicked in, exactly like it's built to.
- **Render and review:** page built, all 4 checklist steps ticked, review passed.

An earlier run (`20261014T161032Z`, gemini-3.7-flash + gemini-3.5-flash-lite) landed on the same numbers.

Then every value got checked by hand against the source table:

| Casino | Welcome bonus | Wagering | Min. deposit |
|---|---|---|---|
| BetMGM Casino | 100% up to 1,000 USD + 25 USD free | 15x | 10 USD |
| Caesars Palace Casino | 100% up to 1,000 USD | 15x | 20 USD |
| bet365 Casino | 100% up to 1,000 USD + 1,000 bonus spins | 20x | 10 USD |

### Generic extractor, live

Now the big question: does the generic path work on a real page, not just in the tests? `EXTRACTOR=generic python run.py` ran against the same page with real Gemini (run `20261014T170352Z`). **Review passed.**

- **Extract:** instead of neat table rows, the AI got 8,505 chars of cleaned page text and had to find the casinos itself.
- **Structure:** gemini-3.5-flash-lite and gemini-3.1-flash-lite each found the **same 3 casinos with the same numbers** as the RotoWire extractor: wagering 15, 15, 20 and minimum deposits 10, 20, 10 USD. Every value was right there in the page text.
- **What that means:** a site with no extractor of its own can still be scraped, with the same checks.

### Failure handling, live

Here's what happens when things go wrong for real:

- **The layout changes.** Pointed at a page with no bonus table, the pipeline retried once, exited with code 1, and wrote the reason to the checklist.
- **Gemini runs out of steam.** When only one model was available (the rest came back 429 or 503), the two-model run **failed safely**. Nothing got published, the checklist said why, and the live page kept the last good data.
- **The AI slips on wording.** In a single-model check, one model wrote "1,000 USD bonus spins". Spins aren't dollars. That's exactly why the bonus wording is never treated as verified (see `models_agree_on_bonus`).
