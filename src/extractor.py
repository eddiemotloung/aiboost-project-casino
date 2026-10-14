"""Step 2: strip the DOM down to one free-text block per casino."""
import json

from bs4 import BeautifulSoup

from common import CASINO_COUNT, RAW_HTML, SOURCE_URL, UNSTRUCTURED, StepError, verify_file

STEP = "extractor"


def extract_blocks(html: str) -> list[dict]:
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
        blocks.append({"casino": cells[0], "source_url": SOURCE_URL, "text": text})
        if len(blocks) == CASINO_COUNT:
            break

    if len(blocks) < CASINO_COUNT:
        raise StepError(f"[{STEP}] found {len(blocks)} casino rows, need {CASINO_COUNT}")
    return blocks


def run() -> None:
    verify_file(RAW_HTML, STEP)
    blocks = extract_blocks(RAW_HTML.read_text(encoding="utf-8"))
    UNSTRUCTURED.write_text(json.dumps(blocks, indent=2, ensure_ascii=False), encoding="utf-8")
    verify_file(UNSTRUCTURED, STEP)
    print(f"[{STEP}] wrote {len(blocks)} text blocks: {', '.join(b['casino'] for b in blocks)}")


if __name__ == "__main__":
    run()
