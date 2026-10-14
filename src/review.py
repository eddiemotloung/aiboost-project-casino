"""Final review: independently re-check a run's ledger against what is on disk.

Doesn't trust a step's own claim of success: every step must be ticked,
every artifact and log must exist and be non-empty, and the published
page must contain every casino from the JSON.
"""
import json
from html import escape
from pathlib import Path

from common import CASINO_JSON, INDEX_HTML, ROOT


def review(run_dir: Path) -> list[str]:
    problems = []
    ledger = json.loads((run_dir / "ledger.json").read_text(encoding="utf-8"))
    for name, step in ledger["steps"].items():
        if step["status"] != "done":
            problems.append(f"{name}: not completed ({step['status']}: {step['error']})")
            continue
        for rel in step["artifacts"] + [(run_dir / "logs" / f"{name}.log").relative_to(ROOT).as_posix()]:
            p = ROOT / rel
            if not p.exists() or p.stat().st_size == 0:
                problems.append(f"{name}: artifact {rel} missing or empty")

    if not problems:
        casinos = json.loads(CASINO_JSON.read_text(encoding="utf-8"))["casinos"]
        page = INDEX_HTML.read_text(encoding="utf-8")
        for c in casinos:
            if escape(c["casino_name"]) not in page:
                problems.append(f"build_page: {c['casino_name']} is in casino.json but not on the page")
    return problems
