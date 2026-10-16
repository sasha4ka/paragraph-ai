"""Python interface to the KaTeX renderer bundled with the project."""

import asyncio
import json
import re
from pathlib import Path
from typing import cast

_RENDERER_DIR = Path(__file__).resolve().parents[3] / "renderer"
KATEX_DIST = _RENDERER_DIR / "node_modules" / "katex" / "dist"
_RENDERER_SCRIPT = _RENDERER_DIR / "render_formula.cjs"
_RENDER_TIMEOUT_SECONDS = 15
_MAX_TEX_LENGTH = 10_000
_UNICODE_VECTOR_ARROW = re.compile(r"([\w])\u20d7", flags=re.UNICODE)


class FormulaRenderError(RuntimeError):
    """Raised when a LaTeX formula cannot be rendered."""


async def render_formula(tex: str, *, display_mode: bool = False) -> str:
    """Render LaTeX to KaTeX HTML using the bundled Node.js script.

    Requires Node.js and the renderer's npm dependencies to be installed.
    """
    if not tex or len(tex) > _MAX_TEX_LENGTH:
        raise ValueError("tex must be a non-empty string of at most 10000 characters")

    # KaTeX rejects the combining vector arrow used by some extracted source text.
    # Convert e.g. "v⃗₀" to the equivalent TeX notation "\\vec{v}₀".
    tex = _UNICODE_VECTOR_ARROW.sub(r"\\vec{\1}", tex)

    try:
        process = await asyncio.create_subprocess_exec(
            "node",
            str(_RENDERER_SCRIPT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise FormulaRenderError("Node.js is not installed or not on PATH") from exc

    payload = json.dumps(
        {"tex": tex, "displayMode": display_mode}, ensure_ascii=False
    ).encode("utf-8")
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(payload), timeout=_RENDER_TIMEOUT_SECONDS
        )
    except TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise FormulaRenderError("KaTeX rendering timed out") from exc

    if process.returncode != 0:
        message = stderr.decode("utf-8", errors="replace").strip()
        raise FormulaRenderError(message or "KaTeX rendering failed")

    try:
        result = cast(dict[str, object], json.loads(stdout))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FormulaRenderError("KaTeX renderer returned invalid JSON") from exc

    html = result.get("html")
    if not isinstance(html, str):
        raise FormulaRenderError("KaTeX renderer returned no HTML")
    return html
