"""Step 4: render data/casino.json into a static, phone-friendly docs/index.html.

The table is rendered at build time, so it works without JavaScript; a small
script adds click-to-sort. casino.json is copied next to the page for download.
"""
import shutil
from html import escape
from urllib.parse import urlparse

from common import CASINO_JSON, DOCS, INDEX_HTML, verify_file
from llm_wrapper import validate

STEP = "build_page"
PUBLIC_JSON = DOCS / "casino.json"

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Casino Bonuses</title>
<style>
  :root {{ --bg: #fff; --fg: #111; --muted: #555; --line: #ddd; --head: #f3f3f3; --link: #0645ad; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #121212; --fg: #eee; --muted: #aaa; --line: #333; --head: #1e1e1e; --link: #8ab4f8; }}
  }}
  body {{ font-family: system-ui, sans-serif; margin: 0 auto; max-width: 960px; padding: 16px; background: var(--bg); color: var(--fg); }}
  h1 {{ font-size: 1.4rem; margin: 0 0 4px; }}
  p.meta {{ color: var(--muted); font-size: .85rem; margin: 0 0 16px; line-height: 1.5; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid var(--line); padding: 8px; text-align: left; vertical-align: top; }}
  th {{ background: var(--head); cursor: pointer; user-select: none; white-space: nowrap; }}
  th[aria-sort="ascending"]::after {{ content: " \\25B2"; }}
  th[aria-sort="descending"]::after {{ content: " \\25BC"; }}
  td.num {{ font-variant-numeric: tabular-nums; }}
  a {{ color: var(--link); }}
  @media (max-width: 640px) {{
    thead {{ display: none; }}
    table, tbody, tr, td {{ display: block; width: 100%; box-sizing: border-box; }}
    tr {{ margin-bottom: 12px; border: 1px solid var(--line); }}
    td {{ border: none; border-bottom: 1px solid var(--line); }}
    td::before {{ content: attr(data-label); display: block; font-weight: 600; font-size: .8rem; color: var(--muted); }}
  }}
</style>
</head>
<body>
<h1>Casino welcome bonuses</h1>
<p class="meta">
  Scraped {scraped_at} from <a href="{source_url}" rel="nofollow noopener">{source_host}</a>.<br>
  Terms structured by {models}; wagering and minimum deposit agreed across models and were checked against the source text.<br>
  Data: <a href="casino.json">casino.json</a>. Click a column header to sort.
</p>
<table id="bonuses">
<thead><tr>
  <th data-type="text">Casino</th><th data-type="text">Welcome bonus</th>
  <th data-type="num">Wagering (x)</th><th data-type="num">Min. deposit</th><th data-type="text">Source</th>
</tr></thead>
<tbody>
{rows}
</tbody>
</table>
<script>
document.querySelectorAll("#bonuses th").forEach((th, col) => {{
  th.addEventListener("click", () => {{
    const asc = th.getAttribute("aria-sort") !== "ascending";
    document.querySelectorAll("#bonuses th").forEach(h => h.removeAttribute("aria-sort"));
    th.setAttribute("aria-sort", asc ? "ascending" : "descending");
    const body = document.querySelector("#bonuses tbody");
    const key = td => th.dataset.type === "num" ? parseFloat(td.dataset.sort) : td.textContent.trim().toLowerCase();
    [...body.rows].sort((a, b) => {{
      const x = key(a.cells[col]), y = key(b.cells[col]);
      return (x > y ? 1 : x < y ? -1 : 0) * (asc ? 1 : -1);
    }}).forEach(r => body.appendChild(r));
  }});
}});
</script>
</body>
</html>
"""

ROW = (
    '<tr><td data-label="Casino">{casino_name}</td>'
    '<td data-label="Welcome bonus">{welcome_bonus}</td>'
    '<td data-label="Wagering (x)" class="num" data-sort="{wagering_requirement}">{wagering_requirement}x</td>'
    '<td data-label="Min. deposit" class="num" data-sort="{deposit_value}">{minimum_deposit}</td>'
    '<td data-label="Source"><a href="{source_url}" rel="nofollow noopener">{source_host}</a></td></tr>'
)


def host(url: str) -> str:
    return urlparse(url).netloc.removeprefix("www.")


def deposit_value(text: str) -> str:
    digits = "".join(ch for ch in text.split()[0] if ch.isdigit() or ch == ".")
    return digits or "0"


def run() -> list:
    data = validate(CASINO_JSON)
    rows = "\n".join(
        ROW.format(
            casino_name=escape(c["casino_name"]),
            welcome_bonus=escape(c["welcome_bonus"]),
            wagering_requirement=int(c["wagering_requirement"]),
            minimum_deposit=escape(c["minimum_deposit"]),
            deposit_value=deposit_value(c["minimum_deposit"]),
            source_url=escape(c["source_url"]),
            source_host=escape(host(c["source_url"])),
        )
        for c in data["casinos"]
    )
    DOCS.mkdir(parents=True, exist_ok=True)
    INDEX_HTML.write_text(TEMPLATE.format(
        rows=rows,
        scraped_at=escape(data["scraped_at"].replace("T", " ").replace("Z", " UTC")),
        source_url=escape(data["source_url"]),
        source_host=escape(host(data["source_url"])),
        models=escape(" and ".join(data["models"])),
    ), encoding="utf-8")
    shutil.copyfile(CASINO_JSON, PUBLIC_JSON)
    verify_file(INDEX_HTML, STEP)
    verify_file(PUBLIC_JSON, STEP)
    print(f"[{STEP}] wrote {INDEX_HTML.name} and {PUBLIC_JSON.name}")
    return [INDEX_HTML, PUBLIC_JSON]


if __name__ == "__main__":
    run()
