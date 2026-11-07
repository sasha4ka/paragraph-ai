import asyncio
from types import SimpleNamespace

from app import openai
from app.logics.summary.models import SourceParagraph
from app.logics.summary.summary_generator import generate_text_summary


def test_text_summary_uses_current_structured_schemas(monkeypatch):
    calls = []
    payloads = {
        "PlannerResult": {"items": [{"id": 1, "title": "Алканы", "question": "Что это?"}]},
        "ExtractionResults": {
            "facts": [
                {
                    "type": "text",
                    "plan_item": 1,
                    "content": "Алканы — углеводороды.",
                    "source_fragment": "Алканы — углеводороды.",
                }
            ]
        },
        "BakerResult": {"blocks": [{"plan_item": 1, "text": "<h2>Алканы</h2>"}]},
    }

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            assert kwargs["api_key"]() == "test-token"

        async def ainvoke(self, messages):
            calls.append("clean")
            return SimpleNamespace(content="Алканы — углеводороды.")

        def with_structured_output(self, schema, *, method):
            assert method == "function_calling"

            async def invoke(messages):
                assert "Алканы" in messages[1][1]
                calls.append(schema.__name__)
                return payloads[schema.__name__]

            return SimpleNamespace(ainvoke=invoke)

    monkeypatch.setattr(openai, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(openai.settings, "openai_api_token", "test-token")

    async def collect():
        return [
            event
            async for event in generate_text_summary(SourceParagraph("Алканы", "Текст"))
        ]

    events = asyncio.run(collect())
    assert calls == ["clean", "PlannerResult", "ExtractionResults", "BakerResult"]
    assert [event.status for event in events] == [
        "cleaning", "planing", "extracting", "baking", "done"
    ]
    assert events[-1].result[0].text == "<h2>Алканы</h2>"
