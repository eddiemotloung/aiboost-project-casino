"""Single entry point: python run.py

Runs the four steps, records each in a checklist ledger (runs/<run_id>/),
then a review pass re-checks everything on disk. If the review finds a
failed or empty step, the pipeline is re-run from that step once before
giving up.
"""
import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import build_page  # noqa: E402
import extractor  # noqa: E402
import fetcher  # noqa: E402
import llm_wrapper  # noqa: E402
from common import ROOT, StepError  # noqa: E402
from ledger import Ledger  # noqa: E402
from review import review  # noqa: E402

PIPELINE = [("fetch", fetcher), ("extract", extractor), ("structure", llm_wrapper), ("build_page", build_page)]
MAX_PASSES = 2


class Tee:
    """Write to the console and the step's log file at once."""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, text):
        for s in self.streams:
            s.write(text)

    def flush(self):
        for s in self.streams:
            s.flush()


def run_step(ledger: Ledger, name: str, module) -> bool:
    ledger.start(name)
    with open(ledger.log_path(name), "a", encoding="utf-8") as log:
        tee = Tee(sys.stdout, log)
        with contextlib.redirect_stdout(tee), contextlib.redirect_stderr(Tee(sys.stderr, log)):
            try:
                artifacts = module.run()
            except Exception as e:  # StepError or anything unexpected (network, parse): record it, don't crash
                print(f"FAILED: {e}", file=sys.stderr)
                ledger.fail(name, str(e))
                return False
    try:
        ledger.done(name, artifacts)
    except StepError as e:
        ledger.fail(name, str(e))
        return False
    return True


def main() -> int:
    ledger = Ledger(ROOT / "runs")
    start = 0
    for attempt in range(1, MAX_PASSES + 1):
        for name, module in PIPELINE[start:]:
            if not run_step(ledger, name, module):
                break
        problems = review(ledger.dir)
        if not problems:
            print(f"Review passed. Checklist: {ledger.dir / 'checklist.md'}")
            return 0
        print(f"Review pass {attempt} found problems:\n  " + "\n  ".join(problems), file=sys.stderr)
        failed = [n for n, _ in PIPELINE if ledger.steps[n]["status"] != "done"] or [PIPELINE[-1][0]]
        start = [n for n, _ in PIPELINE].index(failed[0])
        if attempt < MAX_PASSES:
            print(f"Re-running from step '{PIPELINE[start][0]}'", file=sys.stderr)
    print(f"FAILED after {MAX_PASSES} passes. See {ledger.dir / 'checklist.md'}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
