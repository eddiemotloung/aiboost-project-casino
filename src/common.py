"""Shared paths, config and output verification."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"

RAW_HTML = DATA / "raw_source.html"
UNSTRUCTURED = DATA / "unstructured_cache.txt"
CASINO_JSON = DATA / "casino.json"
INDEX_HTML = DOCS / "index.html"

load_dotenv(ROOT / ".env")

DEFAULT_SOURCE = (
    "https://www.rotowire.com/news/"
    "best-casino-bonuses-in-the-us-this-week-top-welcome-offers-for-new-players-in-2026-120454"
)
SOURCE_URL = os.getenv("CASINO_SOURCE_URL", DEFAULT_SOURCE)
USER_AGENT = "CasinoBonusScreeningBot/1.0 (+https://github.com/; screening task, 1 request/run)"
CASINO_COUNT = 3


class StepError(RuntimeError):
    """Raised when a pipeline step fails or produces unusable output."""


def verify_file(path: Path, step: str) -> None:
    """Fail loudly if a step's output file is missing or empty."""
    if not path.exists():
        raise StepError(f"[{step}] expected output {path} does not exist")
    if path.stat().st_size == 0:
        raise StepError(f"[{step}] output {path} is 0 bytes")
