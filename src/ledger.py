"""Per-run checklist ledger.

Each run gets runs/<run_id>/ with:
  checklist.md   human-readable ledger: a step is only ticked when its artifacts verified
  ledger.json    the same, machine-readable, read by the review step
  logs/<step>.log  everything the step printed
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from common import ROOT, verify_file

STEPS = {
    "fetch": "Fetch source page (robots.txt checked, no block/CAPTCHA)",
    "extract": "Extract casino text (site extractor, or generic page text)",
    "structure": "Structure terms with 2 LLMs; numbers agree and appear in source",
    "build_page": "Render docs/index.html from casino.json",
}


class Ledger:
    def __init__(self, runs_dir: Path):
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.dir = runs_dir / self.run_id
        self.logs = self.dir / "logs"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.steps = {name: {"desc": desc, "status": "pending", "artifacts": [], "error": None, "attempts": 0}
                      for name, desc in STEPS.items()}
        self.save()

    def log_path(self, step: str) -> Path:
        return self.logs / f"{step}.log"

    def start(self, step: str) -> None:
        self.steps[step]["attempts"] += 1
        self.steps[step]["status"] = "running"
        self.save()

    def done(self, step: str, artifacts: list[Path]) -> None:
        for path in artifacts + [self.log_path(step)]:
            verify_file(path, step)
        self.steps[step].update(status="done", error=None,
                                artifacts=[Path(p).relative_to(ROOT).as_posix() for p in artifacts])
        self.save()

    def fail(self, step: str, error: str) -> None:
        self.steps[step].update(status="failed", error=error)
        self.save()

    def save(self) -> None:
        (self.dir / "ledger.json").write_text(
            json.dumps({"run_id": self.run_id, "steps": self.steps}, indent=2), encoding="utf-8")
        lines = [f"# Run {self.run_id}", ""]
        for name, s in self.steps.items():
            box = "x" if s["status"] == "done" else " "
            line = f"- [{box}] **{name}**: {s['desc']}"
            if s["artifacts"]:
                line += f" (artifacts: {', '.join(s['artifacts'])})"
            if s["status"] == "failed":
                line += f"\n  - FAILED (attempt {s['attempts']}): {s['error']}"
            lines.append(line)
        (self.dir / "checklist.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
