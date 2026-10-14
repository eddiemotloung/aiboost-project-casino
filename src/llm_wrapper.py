"""Step 3: turn free-text bonus terms into structured fields with Gemini.

Two different models extract the same blocks independently. Wagering and
minimum deposit must match between them AND appear in the scraped text,
otherwise the run fails instead of publishing a guess.

API key: put it in a `.env` file in the project root (gitignored), e.g.
    LLM_API_KEY=your-key
    GEMINI_MODEL=gemini-3.8-flash
or set it as an environment variable. It is never hard-coded or logged.
"""
import json
import os
import re
import time
from datetime import datetime, timezone

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from common import CASINO_COUNT, CASINO_JSON, SOURCE_URL, UNSTRUCTURED, StepError, verify_file

STEP = "llm_wrapper"
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
FALLBACK_MODELS = [
    "gemini-3.5-flash", "gemini-3.7-flash", "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite", "gemini-flash-latest",
]
CONSENSUS_MODELS = int(os.getenv("CONSENSUS_MODELS", "2"))
RETRIES_PER_MODEL = 3

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "casinos": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "casino_name": {"type": "STRING"},
                    "welcome_bonus": {"type": "STRING"},
                    "wagering_requirement": {"type": "INTEGER"},
                    "minimum_deposit": {"type": "STRING"},
                },
                "required": ["casino_name", "welcome_bonus", "wagering_requirement", "minimum_deposit"],
            },
        }
    },
    "required": ["casinos"],
}

PROMPT = """You extract casino welcome-bonus data from free text scraped from a comparison site.
For each block below return one record, in the same order:
- casino_name: the brand, e.g. "BetMGM Casino" (drop words like "Bonus", "Promo", "Offer")
- welcome_bonus: short normalised form like "100% up to 1,000 USD" (+ extras such as "+ 25 USD free").
  Use ISO currency codes, not symbols ($ = USD). Write numbers in full (1K -> 1,000).
- wagering_requirement: the playthrough multiplier as an integer only (e.g. "15x wagering" -> 15).
- minimum_deposit: amount with ISO currency code, e.g. "10 USD".
Use only facts stated in the text. Do not guess.

Blocks:
{blocks}
"""

FIELDS = ["casino_name", "welcome_bonus", "wagering_requirement", "minimum_deposit", "source_url"]


def get_client() -> genai.Client:
    key = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key:
        raise StepError(f"[{STEP}] no API key: set LLM_API_KEY in .env or the environment")
    return genai.Client(api_key=key)


def ask(client: genai.Client, model: str, prompt: str) -> list[dict] | None:
    """One model, a few retries on overload. Returns parsed records or None if the model is unavailable."""
    config = types.GenerateContentConfig(
        response_mime_type="application/json", response_schema=SCHEMA, temperature=0
    )
    for attempt in range(RETRIES_PER_MODEL):
        try:
            resp = client.models.generate_content(model=model, contents=prompt, config=config)
            return json.loads(resp.text)["casinos"]
        except genai_errors.ServerError as e:  # 5xx: overloaded, worth retrying
            print(f"[{STEP}] {model} attempt {attempt + 1}: HTTP {e.code}, retrying")
            time.sleep(2 ** attempt * 2)
        except genai_errors.ClientError as e:  # 4xx: bad key or unknown model, retrying won't help
            print(f"[{STEP}] {model} rejected request: HTTP {e.code}")
            return None
        except (TypeError, ValueError, KeyError) as e:
            print(f"[{STEP}] {model} returned unusable JSON: {e}")
            return None
    return None


def collect_answers(prompt: str, expected: int) -> dict[str, list[dict]]:
    """Ask models in order until CONSENSUS_MODELS of them give a well-formed answer."""
    client = get_client()  # keep a reference: a temporary client gets closed mid-request
    answers = {}
    for model in [MODEL] + [m for m in FALLBACK_MODELS if m != MODEL]:
        records = ask(client, model, prompt)
        if records is None:
            continue
        if len(records) != expected:
            print(f"[{STEP}] {model} returned {len(records)} records for {expected} blocks, ignoring it")
            continue
        print(f"[{STEP}] {model} answered")
        answers[model] = records
        if len(answers) == CONSENSUS_MODELS:
            return answers
    raise StepError(
        f"[{STEP}] only {len(answers)} of {CONSENSUS_MODELS} required models answered "
        f"({', '.join(answers) or 'none'}); Gemini may be overloaded, try again later"
    )


def number(text: str) -> str | None:
    m = re.search(r"\d[\d,.]*", str(text))
    return m.group(0).replace(",", "").rstrip(".") if m else None


def check_against_source(rec: dict, text: str) -> None:
    """Catch hallucinations: the numbers a model returns must appear in the source text."""
    w = rec.get("wagering_requirement")
    if not re.search(rf"\b{w}\s*[x×]", text, re.IGNORECASE):
        raise StepError(f"[{STEP}] wagering {w}x for {rec.get('casino_name')} not found in source text")
    dep = number(rec.get("minimum_deposit", ""))
    if not dep or not re.search(rf"\$?\b{re.escape(dep)}\b", text.replace(",", "")):
        raise StepError(f"[{STEP}] minimum deposit {rec.get('minimum_deposit')!r} not found in source text")


def reconcile(answers: dict[str, list[dict]], blocks: list[dict]) -> list[dict]:
    """Merge model answers. Hard fields must agree; the bonus text is taken from the primary model."""
    models = list(answers)
    primary = answers[models[0]]
    merged = []
    for i, block in enumerate(blocks):
        recs = [answers[m][i] for m in models]
        for m, rec in zip(models, recs):
            check_against_source(rec, block["text"])
        for field, key in (("wagering_requirement", int), ("minimum_deposit", number)):
            values = {m: key(r[field]) for m, r in zip(models, recs)}
            if len(set(values.values())) > 1:
                raise StepError(f"[{STEP}] models disagree on {field} for {block['casino']}: {values}")
        bonus_numbers = {m: sorted(re.findall(r"\d+", r["welcome_bonus"].replace(",", ""))) for m, r in zip(models, recs)}
        bonus_agrees = len({tuple(v) for v in bonus_numbers.values()}) == 1
        if not bonus_agrees:
            print(f"[{STEP}] note: bonus wording differs for {block['casino']}: "
                  + "; ".join(f"{m}: {r['welcome_bonus']}" for m, r in zip(models, recs)))
        rec = dict(primary[i])
        rec["source_url"] = block["source_url"]  # set by the scraper, never by the model
        rec["models_agree_on_bonus"] = bonus_agrees
        merged.append(rec)
    return merged


def validate(path=CASINO_JSON) -> dict:
    verify_file(path, STEP)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise StepError(f"[{STEP}] {path} is not valid JSON: {e}") from e
    casinos = data.get("casinos", [])
    if len(casinos) != CASINO_COUNT:
        raise StepError(f"[{STEP}] expected {CASINO_COUNT} casinos, got {len(casinos)}")
    for c in casinos:
        missing = [f for f in FIELDS if c.get(f) in (None, "")]
        if missing:
            raise StepError(f"[{STEP}] {c.get('casino_name', '?')} missing fields: {missing}")
        if not isinstance(c["wagering_requirement"], int):
            raise StepError(f"[{STEP}] wagering_requirement must be an integer: {c}")
    return data


def run() -> list:
    verify_file(UNSTRUCTURED, STEP)
    blocks = json.loads(UNSTRUCTURED.read_text(encoding="utf-8"))
    joined = "\n\n".join(f"--- Block {i + 1} ---\n{b['text']}" for i, b in enumerate(blocks))
    answers = collect_answers(PROMPT.format(blocks=joined), len(blocks))
    casinos = reconcile(answers, blocks)
    out = {
        "scraped_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_url": SOURCE_URL,
        "models": list(answers),
        "casinos": casinos,
    }
    CASINO_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    validate()
    print(f"[{STEP}] wrote {len(casinos)} records to {CASINO_JSON.name}; "
          f"wagering and deposit agreed across {', '.join(answers)}")
    return [CASINO_JSON]


if __name__ == "__main__":
    run()
