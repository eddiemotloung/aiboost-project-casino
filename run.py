"""Single entry point: python run.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import build_page  # noqa: E402
import extractor  # noqa: E402
import fetcher  # noqa: E402
import llm_wrapper  # noqa: E402
from common import StepError  # noqa: E402


def main() -> int:
    try:
        for step in (fetcher, extractor, llm_wrapper, build_page):
            step.run()
    except StepError as e:
        print(f"FAILED: {e}", file=sys.stderr)
        return 1
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
