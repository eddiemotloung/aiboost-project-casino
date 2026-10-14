"""Step 2: strip the DOM down to free text the LLM can structure.

Extractors are pluggable, one per source domain:

    @register("example.com")
    def example(html, url) -> list[dict]: ...

A site-specific extractor returns one "row" block per casino. Any domain
without one falls back to `generic`, which returns the whole cleaned page
as a single "page" block and lets the LLM find the casinos in it. Adding a
source is therefore one small function, not a change to the pipeline.
Force a specific extractor with EXTRACTOR=<name> (e.g. EXTRACTOR=generic).
"""
import json
import os
import re
from typing import Callable
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from common import CASINO_COUNT, RAW_HTML, SOURCE_URL, UNSTRUCTURED, StepError, verify_file

STEP = "extractor"
MAX_PAGE_CHARS = 30_000  # keeps the generic prompt small and cheap
MIN_PAGE_CHARS = 200

Extractor = Callable[[str, str], list[dict]]
EXTRACTORS: dict[str, Extractor] = {}


def register(domain: str):
    def wrap(fn: Extractor) -> Extractor:
        EXTRACTORS[domain] = fn
        fn.extractor_name = domain
        return fn
    return wrap


def domain_of(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def pick_extractor(url: str) -> tuple[str, Extractor]:
    forced = os.getenv("EXTRACTOR")
    if forced:
        if forced == "generic":
            return "generic", generic
        if forced not in EXTRACTORS:
            raise StepError(f"[{STEP}] EXTRACTOR={forced!r} unknown; have: generic, {', '.join(EXTRACTORS)}")
        return forced, EXTRACTORS[forced]
    host = domain_of(url)
    for domain, fn in EXTRACTORS.items():
        if host == domain or host.endswith("." + domain):
            return domain, fn
    return "generic", generic


@register("rotowire.com")
def rotowire(html: str, url: str) -> list[dict]:
    """RotoWire bonus articles: one table row per casino."""
    soup = BeautifulSoup(html, "html.parser")
    article = soup.find("article", class_="article") or soup.find("article")
    if article is None:
        raise StepError(f"[{STEP}] no <article> found; page layout changed")
    table = article.find("table")
    if table is None:
        raise StepError(f"[{STEP}] no bonus table found in article; page layout changed")

    headers = [th.get_text(" ", strip=True) for th in table.find("tr").find_all(["th", "td"])]
    blocks = []
    for tr in table.find_all("tr")[1:]:
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) < len(headers) or not cells[0]:
            continue
        # Keep it unstructured on purpose: the LLM step does the structuring.
        text = "\n".join(f"{h}: {c}" for h, c in zip(headers, cells))
        blocks.append({"kind": "row", "casino": cells[0], "source_url": url, "text": text})
        if len(blocks) == CASINO_COUNT:
            break

    if len(blocks) < CASINO_COUNT:
        raise StepError(f"[{STEP}] found {len(blocks)} casino rows, need {CASINO_COUNT}")
    return blocks


def generic(html: str, url: str) -> list[dict]:
    """Any site: the readable text of the main content, for the LLM to read."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form", "iframe"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = re.sub(r"\n\s*\n+", "\n", main.get_text("\n", strip=True))
    if len(text) < MIN_PAGE_CHARS:
        raise StepError(f"[{STEP}] page has only {len(text)} chars of text; nothing to extract")
    return [{"kind": "page", "casino": "(whole page)", "source_url": url, "text": text[:MAX_PAGE_CHARS]}]


def extract_blocks(html: str, url: str = SOURCE_URL) -> list[dict]:
    name, fn = pick_extractor(url)
    blocks = fn(html, url)
    for b in blocks:
        b["extractor"] = name
    return blocks


def run() -> list:
    verify_file(RAW_HTML, STEP)
    blocks = extract_blocks(RAW_HTML.read_text(encoding="utf-8"), SOURCE_URL)
    UNSTRUCTURED.write_text(json.dumps(blocks, indent=2, ensure_ascii=False), encoding="utf-8")
    verify_file(UNSTRUCTURED, STEP)
    name = blocks[0]["extractor"]
    if name == "generic":
        why = "EXTRACTOR=generic set" if os.getenv("EXTRACTOR") else f"no extractor for {domain_of(SOURCE_URL)}"
        print(f"[{STEP}] {why}; using generic page text ({len(blocks[0]['text']):,} chars)")
    else:
        print(f"[{STEP}] {name} extractor wrote {len(blocks)} blocks: {', '.join(b['casino'] for b in blocks)}")
    return [UNSTRUCTURED]


if __name__ == "__main__":
    run()
