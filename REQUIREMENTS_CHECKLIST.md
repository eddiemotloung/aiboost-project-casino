# Requirements checklist

Every line of the brief. Where it's met. The test that proves it. No "trust me" anywhere.

Want to check it yourself? Run `python -m pytest -v`. The tests run offline: the AI is swapped for a fake client, and the real `data/` files in the repo are checked as evidence.

**Where things stand:** the last full live run, `20261014T170520Z`, passed review with all 4 steps ticked (models gemini-3.5-flash-lite and gemini-flash-latest). The generic extractor passed its own live run too (`20261014T170352Z`), with the same results. And 35 out of 35 tests pass: 26 for the brief, plus 9 for pluggable sources and rate limits.

## 1. Scraper script

| Requirement | Where | Proof (test) | Status |
|---|---|---|---|
| Pulls 3 casinos | `src/extractor.py` takes the first 3 rows of the bonus table | `test_pulls_exactly_3_casinos_from_one_public_source` | ✅ |
| From one public source (a casino promo page or a comparison site) | RotoWire comparison article, `CASINO_SOURCE_URL` | same test: all `source_url` values equal the one article | ✅ |
| Extracts four fields per casino | `src/llm_wrapper.py` schema | `test_committed_json_has_3_casinos_with_the_4_fields` | ✅ |
| Writes them to a JSON file | `data/casino.json` | same test + `test_validation_rejects_bad_json` | ✅ |
| Welcome bonus, e.g. "100% up to 500 EUR" | `welcome_bonus`, e.g. "100% up to 1,000 USD" | `test_committed_json_has_3_casinos_with_the_4_fields` | ✅ |
| Wagering requirement (multiplier), e.g. 35 | `wagering_requirement`, an integer (15, 15, 20) | same | ✅ |
| Minimum deposit, e.g. "20 EUR" | `minimum_deposit`, e.g. "20 USD" | same (format `<number> <ISO code>`) | ✅ |
| Source URL: link to the page it was pulled from | `source_url`, set by the scraper, not the model | same | ✅ |
| Uses a language model to turn free-text terms into structured fields | Gemini via `google-genai`, JSON schema output | `test_llm_receives_the_free_text_and_produces_the_json` | ✅ |
| Runs with a single command | `python run.py` | `test_single_command_runs_all_steps_and_ticks_checklist` | ✅ |
| Respects robots.txt | `fetcher.check_robots()` runs before any request | `test_respects_robots_txt` (page is never requested if disallowed) | ✅ |
| Doesn't bypass logins, CAPTCHAs or blocks; if blocked, switch source | stops on 401/403/429/503 or a CAPTCHA page, honest bot User-Agent | `test_stops_when_blocked_instead_of_bypassing` ×4, `test_stops_on_captcha_page`, `test_sends_identifying_user_agent` | ✅ |
| Typing the data in by hand doesn't count | every wagering and deposit number in `casino.json` is traced back to the saved `data/raw_source.html` | `test_committed_json_matches_the_scraped_page` | ✅ |

## 2. Web page

| Requirement | Where | Proof (test) | Status |
|---|---|---|---|
| A table of the 3 casinos | `docs/index.html` | `test_page_is_a_table_generated_from_the_json` | ✅ |
| Generated from the JSON file | `src/build_page.py` reads `data/casino.json` | same + `test_published_page_matches_committed_json` | ✅ |
| Readable on a phone | viewport meta; rows become stacked cards under 640px | `test_page_is_readable_on_a_phone` | ✅ |
| Published on a free host | GitHub Pages from `/docs`: https://eddiemotloung.github.io/aiboost-project-casino/ | checked live: page loads logged out, shows all 3 casinos, `casino.json` downloads | ✅ |

## 3. Submission

| Item | Status |
|---|---|
| Link to the live page | ✅ https://eddiemotloung.github.io/aiboost-project-casino/ |
| Git repo with the script, the JSON output and a README (install + run) | ✅ https://github.com/eddiemotloung/aiboost-project-casino (public) |
| Written part (production plan for 200 casinos) | ✍️ In the submission |
| Five lines on AI: the tool used and one place it was wrong | ✍️ In the submission |
| How long it took | ✍️ In the submission. The commit timestamps in the git history back it up |

## Extra safeguards beyond the brief

The brief didn't ask for these. They're here anyway, and they're tested.

- **Hallucination guard:** if the AI returns a number that isn't in the source text, the run stops (`test_llm_hallucination_is_rejected`).
- **Two-model agreement:** two models have to agree on wagering and deposit (`test_models_must_agree`).
- **Overload fallback:** retries, then moves to the next model (`test_overloaded_model_falls_back`). A missing API key gives a clear error (`test_no_api_key_gives_clear_error`).
- **No silent failures:** an empty or missing output stops the run (`test_missing_or_empty_output_raises`). So does a step that says it worked but wrote an empty file (`test_step_that_claims_success_but_writes_nothing_fails`).
- **Retry and report:** a failed step gets one retry, then it's reported in `runs/<id>/checklist.md` (`test_failed_step_is_retried_then_reported`).
- **Safe page:** scraped text is HTML-escaped on the page (`test_page_escapes_scraped_text`).
- **No secrets in the repo:** no API key or `.env` is committed (`test_api_key_is_not_committed`), and a pre-commit hook in `.githooks/` blocks any commit that contains one.

## Added after review

- **Pluggable sources.** One extractor per domain, plus a generic fallback for any site. This exists because @eddiemotloung pointed out that the extractor was hard-wired to one site. Tests: `test_rotowire_urls_use_the_rotowire_extractor`, `test_unknown_domain_falls_back_to_generic`, `test_extractor_can_be_forced`, `test_adding_a_source_is_one_registered_function`, `test_generic_extractor_keeps_content_and_drops_noise`, `test_generic_extractor_rejects_empty_page`, `test_generic_page_mode_end_to_end`, `test_models_must_pick_the_same_casino`.
- **Rate limits.** A 429 gets waited out and retried, not skipped (`test_rate_limited_model_is_retried_not_skipped`).

## Where this goes beyond or differs from the brief

- **Extra fields:** `casino_name` (the table needs it) and `models_agree_on_bonus`. All 4 required fields are there, with exactly the meaning the brief asked for.
- **Currency:** USD instead of EUR, because the source lists US offers.
