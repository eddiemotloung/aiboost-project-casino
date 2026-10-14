"""Step 1: fetch the raw source page, respecting robots.txt."""
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from common import RAW_HTML, SOURCE_URL, USER_AGENT, StepError, verify_file

STEP = "fetcher"


def check_robots(url: str) -> None:
    parts = urlparse(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    rp = RobotFileParser(robots_url)
    rp.read()
    if not rp.can_fetch(USER_AGENT, url):
        raise StepError(f"[{STEP}] robots.txt at {robots_url} disallows {url}; pick another source")


def fetch(url: str = SOURCE_URL) -> str:
    check_robots(url)
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    # 401/403/429 mean we are blocked or rate limited: stop, don't try to get around it.
    if resp.status_code in (401, 403, 429, 503):
        raise StepError(f"[{STEP}] blocked by source (HTTP {resp.status_code}); switch source")
    resp.raise_for_status()
    lowered = resp.text.lower()
    if "captcha" in lowered and "<article" not in lowered:
        raise StepError(f"[{STEP}] source served a CAPTCHA page; switch source")
    return resp.text


def run() -> None:
    RAW_HTML.parent.mkdir(parents=True, exist_ok=True)
    RAW_HTML.write_text(fetch(), encoding="utf-8")
    verify_file(RAW_HTML, STEP)
    print(f"[{STEP}] saved {RAW_HTML.stat().st_size:,} bytes from {SOURCE_URL}")


if __name__ == "__main__":
    run()
