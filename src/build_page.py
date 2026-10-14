"""Step 4: render data/casino.json into a static, phone-friendly docs/index.html."""
from datetime import datetime, timezone
from html import escape

from common import CASINO_JSON, INDEX_HTML, verify_file
from llm_wrapper import validate

STEP = "build_page"

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Casino Bonuses</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 0; padding: 16px; background: #fff; color: #111; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 4px; }}
  p.meta {{ color: #555; font-size: .85rem; margin: 0 0 16px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }}
  th {{ background: #f3f3f3; }}
  a {{ color: #0645ad; word-break: break-all; }}
  @media (max-width: 640px) {{
    thead {{ display: none; }}
    table, tbody, tr, td {{ display: block; width: 100%; box-sizing: border-box; }}
    tr {{ margin-bottom: 12px; border: 1px solid #ddd; }}
    td {{ border: none; border-bottom: 1px solid #eee; }}
    td::before {{ content: attr(data-label); display: block; font-weight: 600; font-size: .8rem; color: #555; }}
  }}
</style>
</head>
<body>
<h1>Casino welcome bonuses</h1>
<p class="meta">Generated from data/casino.json on {generated}. Terms change often, so check the source.</p>
<table>
<thead><tr><th>Casino</th><th>Welcome bonus</th><th>Wagering (x)</th><th>Min. deposit</th><th>Source</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
</body>
</html>
"""

ROW = (
    '<tr><td data-label="Casino">{casino_name}</td>'
    '<td data-label="Welcome bonus">{welcome_bonus}</td>'
    '<td data-label="Wagering (x)">{wagering_requirement}</td>'
    '<td data-label="Min. deposit">{minimum_deposit}</td>'
    '<td data-label="Source"><a href="{source_url}" rel="nofollow noopener">{source_host}</a></td></tr>'
)


def run() -> None:
    casinos = validate(CASINO_JSON)
    rows = "\n".join(
        ROW.format(
            **{k: escape(str(v)) for k, v in c.items()},
            source_host="rotowire.com" if "rotowire.com" in c["source_url"] else escape(c["source_url"]),
        )
        for c in casinos
    )
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    INDEX_HTML.parent.mkdir(parents=True, exist_ok=True)
    INDEX_HTML.write_text(TEMPLATE.format(rows=rows, generated=generated), encoding="utf-8")
    verify_file(INDEX_HTML, STEP)
    print(f"[{STEP}] wrote {INDEX_HTML}")


if __name__ == "__main__":
    run()
