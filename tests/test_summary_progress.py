import asyncio
from importlib import import_module
from types import SimpleNamespace

from app.logics.summary.models import BakedBlock
from app.logics.summary.summary_generator import SummaryGeneratorEvent
from app.states import Summarize

router = import_module("app.handlers.summarize.router")


def test_summary_handler_reports_each_phase_and_sends_result(monkeypatch):
    edits = []
    sent = []
    states = []

    async def edit(**kwargs):
        edits.append(kwargs["text"])

    async def answer(**kwargs):
        sent.append(kwargs["text"])
        return SimpleNamespace(message=SimpleNamespace(body=None, edit=edit))

    async def set_state(state):
        states.append(state)

    async def get_data():
        return {
            "book_path": "book.json",
            "paragraphs": [("3", SimpleNamespace(title="Алканы"))],
        }

    async def resolve(query, titles):
        return ["3"]

    async def get_text(ids):
        return "Алканы — углеводороды."

    async def generate(source):
        assert source.paragraph_id == 3
        for status in ("cleaning", "planing", "extracting", "baking"):
            yield SummaryGeneratorEvent(status, False)
        yield SummaryGeneratorEvent("done", True, result=[BakedBlock(plan_item=1, text="Конспект")])

    book = SimpleNamespace(metadata=SimpleNamespace(title="Химия"), get_text=get_text)
    monkeypatch.setattr(router, "resolve_paragraphs", resolve)
    monkeypatch.setattr(router, "generate_text_summary", generate)
    monkeypatch.setattr(router.BooksRepository, "get_book", lambda self, path: book)
    event = SimpleNamespace(
        from_user=SimpleNamespace(user_id=1),
        message=SimpleNamespace(
            body=SimpleNamespace(text="3", mid="test"), answer=answer
        ),
    )
    asyncio.run(router.select_paragraphs(event, SimpleNamespace(get_data=get_data, set_state=set_state)))

    assert len(edits) == 4
    assert sent == ["Готовлю конспект ⏳", "Конспект"]
    assert states == [Summarize.processing, Summarize.chat_mode]
