import asyncio
import json

import pytest

from app.logics.layout import latex
from app.logics.layout.latex import FormulaRenderError, render_formula


class FakeProcess:
    def __init__(self, stdout: bytes, stderr: bytes = b"", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.payload: bytes | None = None

    async def communicate(self, payload: bytes) -> tuple[bytes, bytes]:
        self.payload = payload
        return self.stdout, self.stderr

    def kill(self) -> None:
        raise AssertionError("Unexpected process kill")


def test_render_formula_invokes_katex_and_returns_html(monkeypatch: pytest.MonkeyPatch):
    process = FakeProcess(b'{"html":"<span class=\\"katex\\">x</span>"}')
    invocation: dict[str, object] = {}

    async def fake_create_subprocess_exec(*args: str, **kwargs: object) -> FakeProcess:
        invocation["args"] = args
        invocation["kwargs"] = kwargs
        return process

    monkeypatch.setattr(
        latex.asyncio, "create_subprocess_exec", fake_create_subprocess_exec
    )

    result = asyncio.run(render_formula(r"\frac{a}{b}", display_mode=True))

    assert result == '<span class="katex">x</span>'
    assert invocation["args"] == ("node", str(latex._RENDERER_SCRIPT))
    assert process.payload is not None
    assert json.loads(process.payload) == {
        "tex": r"\frac{a}{b}",
        "displayMode": True,
    }


def test_render_formula_reports_katex_errors(monkeypatch: pytest.MonkeyPatch):
    process = FakeProcess(b"", b"KaTeX parse error", returncode=1)

    async def fake_create_subprocess_exec(*args: str, **kwargs: object) -> FakeProcess:
        return process

    monkeypatch.setattr(
        latex.asyncio, "create_subprocess_exec", fake_create_subprocess_exec
    )

    with pytest.raises(FormulaRenderError, match="KaTeX parse error"):
        asyncio.run(render_formula("\\bad"))


def test_render_formula_validates_input():
    with pytest.raises(ValueError, match="non-empty string"):
        asyncio.run(render_formula(""))


def test_render_formula_converts_unicode_vector_arrows(monkeypatch: pytest.MonkeyPatch):
    process = FakeProcess(b'{"html":"<span class=\\"katex\\">vector</span>"}')

    async def fake_create_subprocess_exec(*args: str, **kwargs: object) -> FakeProcess:
        return process

    monkeypatch.setattr(
        latex.asyncio, "create_subprocess_exec", fake_create_subprocess_exec
    )

    asyncio.run(render_formula("v⃗ = v⃗₀ + a⃗t"))

    assert process.payload is not None
    assert json.loads(process.payload) == {
        "tex": r"\vec{v} = \vec{v}₀ + \vec{a}t",
        "displayMode": False,
    }
