import asyncio
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.logics.summary.models import BakedBlock

summarize_router = import_module("app.handlers.summarize.router")


def test_card_blocks_are_rendered_and_sent_with_exit_on_last_card(monkeypatch):
    rendered: list[str] = []
    sent = []

    async def fake_render(html: str, output: Path) -> None:
        rendered.append(html)
        output.write_bytes(b"fake image")

    class FakeInputMedia:
        def __init__(self, path: str):
            self.path = path

    class FakeMessage:
        async def answer(
            self, *, attachments: list[object], text: str | None = None
        ) -> None:
            sent.append((text, attachments))

    monkeypatch.setattr(summarize_router, "render_html", fake_render)
    monkeypatch.setattr(summarize_router, "InputMedia", FakeInputMedia)
    event = SimpleNamespace(message=FakeMessage())
    blocks = [
        BakedBlock(
            plan_item=index,
            text=(
                f"<card-title>Title {index}</card-title>"
                "<card-body><p>Body</p></card-body>"
            ),
        )
        for index in range(1, 26)
    ]

    asyncio.run(summarize_router._send_card_blocks(event, blocks))

    assert rendered == [block.text for block in blocks]
    assert [len(attachments) for _, attachments in sent] == [12, 12, 1, 1]
    assert all(text is None for text, _ in sent)
    assert all(
        isinstance(attachment, FakeInputMedia)
        for _, attachments in sent[:3]
        for attachment in attachments
    )
    assert all(isinstance(attachment, FakeInputMedia) for attachment in sent[0][1])
    assert all(isinstance(attachment, FakeInputMedia) for attachment in sent[1][1])
    assert isinstance(sent[2][1][0], FakeInputMedia)
    assert len(sent[3][1]) == 1


@pytest.mark.parametrize("mode", ["text", "cards"])
def test_workflow_start_persists_mode_and_uses_shared_book_picker(monkeypatch, mode):
    class FakeContext:
        data = None
        state = None

        async def update_data(self, **data):
            self.data = data

        async def set_state(self, state):
            self.state = state

    class FakeMessage:
        edited = None

        async def edit(self, *, text: str, attachments: list[object]):
            self.edited = (text, attachments)

    class FakeEvent:
        message = FakeMessage()

    monkeypatch.setattr(
        summarize_router.BooksRepository,
        "list_books",
        lambda _self: [("Book", "/books/book.pdf", "ready")],
    )
    monkeypatch.setattr(
        summarize_router, "compile_books_list", lambda _books: ["1 - Book"]
    )
    context = FakeContext()
    event = FakeEvent()

    asyncio.run(summarize_router._start_summarize_workflow(event, context, mode))

    assert context.data["summary_mode"] == mode
    assert context.state == summarize_router.Summarize.select_book
    assert event.message.edited[0] == "Выберите книгу:\n1 - Book"
