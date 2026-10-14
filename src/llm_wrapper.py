"""Step 3: turn free-text bonus terms into structured fields with Gemini.

API key: put it in a `.env` file in the project root (gitignored), e.g.
    LLM_API_KEY=your-key
    GEMINI_MODEL=gemini-3.8-flash
or set it as an environment variable. It is never hard-coded or logged.
"""
import json
import os
import re
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from common import CASINO_COUNT, CASINO_JSON, UNSTRUCTURED, StepError, verify_file

STEP = "llm_wrapper"
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-latest"]

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
  Use ISO currency codes, not symbols ($ = USD).
- wagering_requirement: the playthrough multiplier as an integer only (e.g. "15x wagering" -> 15).
- minimum_deposit: amount with ISO currency code, e.g. "10 USD".
Use only facts stated in the text. Do not guess.

Blocks:
{blocks}
"""


def get_client() -> genai.Client:
    key = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key:
        raise StepError(f"[{STEP}] no API key: set LLM_API_KEY in .env or the environment")
    return genai.Client(api_key=key)


def call_model(prompt: str):
    """Call the configured model, retrying on overload, then falling back to other models."""
    client = get_client()  # keep a reference: a temporary client gets closed mid-request
    config = types.GenerateContentConfig(
        response_mime_type="application/json", response_schema=SCHEMA, temperature=0
    )
    last_error = None
    for model in [MODEL] + [m for m in FALLBACK_MODELS if m != MODEL]:
        for attempt in range(4):
            try:
                resp = client.models.generate_content(model=model, contents=prompt, config=config)
                print(f"[{STEP}] model {model} answered")
                return resp, model
            except genai_errors.ServerError as e:  # 5xx: overloaded, worth retrying
                last_error = e
                print(f"[{STEP}] {model} attempt {attempt + 1} failed: {e.code}; retrying")
                time.sleep(2 ** attempt * 2)
            except genai_errors.ClientError as e:  # 4xx: bad key or model, retrying won't help
                last_error = e
                print(f"[{STEP}] {model} rejected request: {e.code}; trying next model")
                break
    raise StepError(f"[{STEP}] all models failed; last error: {last_error}")


def structure(blocks: list[dict]) -> tuple[list[dict], str]:
    joined = "\n\n".join(f"--- Block {i + 1} ---\n{b['text']}" for i, b in enumerate(blocks))
    resp, model = call_model(PROMPT.format(blocks=joined))
    try:
        records = json.loads(resp.text)["casinos"]
    except (TypeError, ValueError, KeyError) as e:
        raise StepError(f"[{STEP}] model returned unusable JSON: {e}") from e
    if len(records) != len(blocks):
        raise StepError(f"[{STEP}] model returned {len(records)} records for {len(blocks)} blocks")

    # source_url comes from the scraper, never from the model.
    for rec, block in zip(records, blocks):
        rec["source_url"] = block["source_url"]
        check_against_source(rec, block["text"])
    return records, model


def check_against_source(rec: dict, text: str) -> None:
    """Catch hallucinations: the numbers the model returns must appear in the source text."""
    w = rec.get("wagering_requirement")
    if not re.search(rf"\b{w}\s*[x×]", text, re.IGNORECASE):
        raise StepError(f"[{STEP}] wagering {w}x for {rec.get('casino_name')} not found in source text")
    dep = re.search(r"\d[\d,]*", rec.get("minimum_deposit", ""))
    if not dep or dep.group(0) not in text:
        raise StepError(f"[{STEP}] minimum deposit {rec.get('minimum_deposit')!r} not found in source text")


def validate(path=CASINO_JSON) -> list[dict]:
    verify_file(path, STEP)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise StepError(f"[{STEP}] {path} is not valid JSON: {e}") from e
    casinos = data.get("casinos", [])
    if len(casinos) != CASINO_COUNT:
        raise StepError(f"[{STEP}] expected {CASINO_COUNT} casinos, got {len(casinos)}")
    fields = ["casino_name", "welcome_bonus", "wagering_requirement", "minimum_deposit", "source_url"]
    for c in casinos:
        missing = [f for f in fields if c.get(f) in (None, "")]
        if missing:
            raise StepError(f"[{STEP}] {c.get('casino_name', '?')} missing fields: {missing}")
        if not isinstance(c["wagering_requirement"], int):
            raise StepError(f"[{STEP}] wagering_requirement must be an integer: {c}")
    return casinos


def run() -> None:
    verify_file(UNSTRUCTURED, STEP)
    blocks = json.loads(UNSTRUCTURED.read_text(encoding="utf-8"))
    records, model = structure(blocks)
    CASINO_JSON.write_text(json.dumps({"casinos": records}, indent=2, ensure_ascii=False), encoding="utf-8")
    validate()
    print(f"[{STEP}] wrote {len(records)} structured records to {CASINO_JSON.name} using {model}")


if __name__ == "__main__":
    run()
