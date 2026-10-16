"""Render a card from HTML read on stdin.

Usage: uv run python scripts/render_card.py output.png < card.html
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.logics.layout.renderer import render_html

MAX_INPUT_CHARS = 1_000_000


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a card from HTML on stdin")
    parser.add_argument("output", type=Path, help="Output image path (.png or .jpg)")
    args = parser.parse_args(argv)

    html_text = sys.stdin.read(MAX_INPUT_CHARS + 1)
    if len(html_text) > MAX_INPUT_CHARS:
        print("Input is too large", file=sys.stderr)
        return 2
    if not html_text.strip():
        print("No card HTML received on stdin", file=sys.stderr)
        return 2

    try:
        asyncio.run(render_html(html_text, args.output))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
