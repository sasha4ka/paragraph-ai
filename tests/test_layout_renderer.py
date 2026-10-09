from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.logics.layout import renderer
from app.logics.layout.renderer import (
    SINGLE_COLUMN_SIZE,
    TWO_COLUMN_SIZE,
    render_html,
)


class FakePage:
    def __init__(self, use_two_columns: bool, content_fits: bool = True):
        self.use_two_columns = use_two_columns
        self.content_fits = content_fits
        self.viewport: dict[str, int] | None = None
        self.document: str | None = None
        self.screenshot_options: dict[str, object] | None = None

    async def set_content(self, document: str, wait_until: str) -> None:
        assert wait_until == "load"
        self.document = document

    async def evaluate(self, script: str) -> bool:
        if "scrollHeight" in script:
            return self.use_two_columns
        return self.content_fits

    async def set_viewport_size(self, viewport: dict[str, int]) -> None:
        self.viewport = viewport

    async def screenshot(self, **options: object) -> None:
        self.screenshot_options = options


class FakeBrowser:
    def __init__(self, page: FakePage):
        self.page = page
        self.initial_viewport: dict[str, int] | None = None
        self.closed = False

    async def new_page(
        self, viewport: dict[str, int], device_scale_factor: int
    ) -> FakePage:
        self.initial_viewport = viewport
        assert device_scale_factor == 1
        return self.page

    async def close(self) -> None:
        self.closed = True


class FakePlaywrightManager:
    def __init__(self, browser: FakeBrowser):
        self.browser = browser

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    @property
    def chromium(self) -> FakePlaywrightManager:
        return self

    async def launch(self) -> FakeBrowser:
        return self.browser


def _patch_playwright(monkeypatch: pytest.MonkeyPatch, page: FakePage) -> FakeBrowser:
    browser = FakeBrowser(page)
    monkeypatch.setattr(
        renderer, "async_playwright", lambda: FakePlaywrightManager(browser)
    )
    return browser


def test_render_dimensions_are_fixed_by_column_count():
    assert SINGLE_COLUMN_SIZE == (800, 1000)
    assert TWO_COLUMN_SIZE == (1600, 1000)


def test_render_html_rejects_invalid_card_markup(tmp_path: Path):
    with pytest.raises(ValueError, match="Invalid card HTML"):
        asyncio.run(render_html("<p>Not a card</p>", tmp_path / "card.png"))


def test_render_html_uses_single_column_and_applies_card_style(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    page = FakePage(use_two_columns=False)
    browser = _patch_playwright(monkeypatch, page)
    output = tmp_path / "card.png"

    asyncio.run(
        render_html(
            "<card-title>Title</card-title><card-body>"
            "<p>Short <inline-formula>x + y</inline-formula></p>"
            "<formula>x = y</formula></card-body>",
            output,
        )
    )

    assert page.document is not None
    assert "linear-gradient(30deg, rgba(42, 123, 155, 1) 0%" in page.document
    assert "text-align: center" in page.document
    assert "background: rgba(255, 255, 255, .58)" in page.document
    assert "backdrop-filter: blur(24px) saturate(140%)" in page.document
    assert "color: #8659ab" in page.document
    assert 'content: "[Формула]"' in page.document
    assert 'content: "[формула]"' in page.document
    assert browser.initial_viewport == {"width": 800, "height": 1000}
    assert page.viewport is None
    assert page.screenshot_options == {
        "path": str(output),
        "type": "png",
        "full_page": False,
    }
    assert browser.closed


def test_render_html_switches_to_two_columns_for_overflow(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    page = FakePage(use_two_columns=True)
    browser = _patch_playwright(monkeypatch, page)
    output = tmp_path / "card.jpg"

    asyncio.run(
        render_html(
            "<card-title>Title</card-title><card-body><p>Long</p></card-body>",
            output,
        )
    )

    assert page.viewport == {"width": 1600, "height": 1000}
    assert page.screenshot_options == {
        "path": str(output),
        "type": "jpeg",
        "quality": 90,
        "full_page": False,
    }
    assert browser.closed


def test_render_html_rejects_content_that_overflows_two_columns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    page = FakePage(use_two_columns=True, content_fits=False)
    browser = _patch_playwright(monkeypatch, page)

    with pytest.raises(ValueError, match="split it across multiple cards"):
        asyncio.run(
            render_html(
                "<card-title>Title</card-title><card-body><p>Too long</p></card-body>",
                tmp_path / "card.png",
            )
        )

    assert page.screenshot_options is None
    assert browser.closed
