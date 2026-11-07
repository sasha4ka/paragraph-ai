from __future__ import annotations

import io
from pathlib import Path

import pytest

from scripts import render_card


def test_cli_reads_card_from_stdin_and_renders_to_requested_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    card_html = "<card-title>Title</card-title><card-body><p>Body</p></card-body>"
    output = tmp_path / "card.png"
    rendered: list[tuple[str, Path]] = []

    async def fake_render_html(html_text: str, output_path: Path) -> None:
        rendered.append((html_text, output_path))

    monkeypatch.setattr(render_card.sys, "stdin", io.StringIO(card_html))
    monkeypatch.setattr(render_card, "render_html", fake_render_html)

    exit_code = render_card.main([str(output)])

    assert exit_code == 0
    assert rendered == [(card_html, output)]
    assert capsys.readouterr().out.strip() == str(output)


def test_cli_rejects_empty_stdin(monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setattr(render_card.sys, "stdin", io.StringIO("  \n"))

    assert render_card.main(["card.png"]) == 2
    assert "No card HTML" in capsys.readouterr().err


def test_cli_reports_render_errors(monkeypatch: pytest.MonkeyPatch, capsys):
    async def failed_render(html_text: str, output_path: Path) -> None:
        raise ValueError("invalid card")

    monkeypatch.setattr(render_card.sys, "stdin", io.StringIO("<card />"))
    monkeypatch.setattr(render_card, "render_html", failed_render)

    assert render_card.main(["card.png"]) == 1
    assert "invalid card" in capsys.readouterr().err
