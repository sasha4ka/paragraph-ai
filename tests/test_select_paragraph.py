import asyncio
from types import SimpleNamespace

from app.logics.select_paragraph import select_paragraphs


class FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.messages = None

    async def parse(self, **kwargs):
        self.messages = kwargs["messages"]
        return self.response


class FakeClient:
    def __init__(self, response):
        self.chat = SimpleNamespace(completions=FakeCompletions(response))


def test_select_paragraphs_resolves_human_title_to_ids():
    parsed = SimpleNamespace(paragraph_ids=["12", "18"])
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed, content=None))]
    )
    client = FakeClient(response)

    selected = asyncio.run(
        select_paragraphs(
            "Параллельность прямых и задачи",
            {"12": "Параллельность прямых", "18": "Задачи на построение"},
            client=client,
        )
    )

    assert selected == ["12", "18"]
    assert "Параллельность прямых" in client.chat.completions.messages[1]["content"]