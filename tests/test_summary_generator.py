import asyncio

from app.logics.summary import summary_generator
from app.logics.summary.models import ParagraphSummary, SourceParagraph, SynthesisResult


def test_generate_summary_uses_langchain_structured_outputs(monkeypatch):
    requested_schemas = []
    system_prompts = []

    responses = {
        "_ExtractedInformation": {
            "objects": [{"type": "термин", "content": "Первое понятие"}]
        },
        "ParagraphSummary": {
            "summary": "Краткое объяснение.",
            "key_points": ["Главный тезис."],
        },
        "ParagraphResult": {
            "summary": {
                "summary": "Проверенное объяснение.",
                "key_points": ["Проверенный тезис."],
            },
            "info_objects": [{"type": "термин", "content": "Проверенное понятие"}],
        },
        "SynthesisResult": {
            "summary_block": "Общий конспект.",
            "information_block": "| Тип | Сведение |\n|---|---|\n| Термин | Понятие |",
        },
    }

    class FakeRunnable:
        def __init__(self, schema):
            self.schema = schema

        async def ainvoke(self, messages):
            assert messages[0][0] == "system"
            assert messages[1][0] == "human"
            system_prompts.append(messages[0][1])
            return responses[self.schema.__name__]

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            assert kwargs["model"] == summary_generator.settings.default_model
            assert kwargs["api_key"]() == "test-token"

        def with_structured_output(self, schema, *, method):
            assert method == "function_calling"
            requested_schemas.append(schema.__name__)
            return FakeRunnable(schema)

    monkeypatch.setattr(summary_generator, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(summary_generator.settings, "openai_api_token", "test-token")

    result = asyncio.run(
        summary_generator.generate_summary(
            [SourceParagraph(title="Тема", text="Исходный учебный текст.")]
        )
    )

    assert isinstance(result, SynthesisResult)
    assert result.summary_block == "Общий конспект."
    assert result.information_block.startswith("| Тип | Сведение |")
    assert requested_schemas == [
        "_ExtractedInformation",
        "ParagraphSummary",
        "ParagraphResult",
        "SynthesisResult",
    ]
    assert "для подготовки к устному ответу" in system_prompts[-1]
    assert "краткий конспект" in system_prompts[-1]
    assert "180–220 токенов" in system_prompts[-1]
    assert "100 русских слов" in system_prompts[-1]
    assert "Markdown-таблицы" in system_prompts[-1]


def test_generate_summary_with_events_reports_each_phase(monkeypatch):
    async def extract(paragraph):
        await asyncio.sleep(0.01 if paragraph.paragraph_id == 1 else 0)
        return []

    async def summarize(_paragraph):
        from app.logics.summary.models import ParagraphSummary

        return ParagraphSummary(summary="Кратко.", key_points=[])

    async def verify(_paragraph, result):
        return result

    async def synthesize(_results):
        return SynthesisResult(summary_block="Готово", information_block="")

    monkeypatch.setattr(summary_generator, "_extract_objects", extract)
    monkeypatch.setattr(summary_generator, "_summarize_paragraph", summarize)
    monkeypatch.setattr(summary_generator, "_verify", verify)
    monkeypatch.setattr(summary_generator, "_synthesis", synthesize)

    async def collect_events():
        return [
            event
            async for event in summary_generator.generate_summary_with_events(
                [
                    SourceParagraph("Тема 1", "Текст 1", paragraph_id=1),
                    SourceParagraph("Тема 2", "Текст 2", paragraph_id=2),
                ]
            )
        ]

    events = asyncio.run(collect_events())
    statuses = [event.status for event in events]

    assert statuses[:2] == ["extracting", "extracting"]
    assert "waiting_for_others" in statuses
    assert "summarization" in statuses
    assert "verifying" in statuses
    assert statuses[-2:] == ["synthesis", "synthesis"]
    assert events[-1].result == SynthesisResult(
        summary_block="Готово", information_block=""
    )


def test_each_paragraph_advances_without_waiting_for_other_paragraphs(monkeypatch):
    first_extract_started = asyncio.Event()
    release_first_extract = asyncio.Event()
    call_order = []

    async def extract(paragraph):
        if paragraph.paragraph_id == 1:
            first_extract_started.set()
            await release_first_extract.wait()
            call_order.append("extract_done_1")
        else:
            await first_extract_started.wait()
            call_order.append("extract_done_2")
        return []

    async def summarize(paragraph):
        call_order.append(f"summarize_{paragraph.paragraph_id}")
        return ParagraphSummary(summary="Кратко.", key_points=[])

    async def verify(_paragraph, result):
        return result

    async def synthesize(_results):
        return SynthesisResult(summary_block="Готово", information_block="")

    monkeypatch.setattr(summary_generator, "_extract_objects", extract)
    monkeypatch.setattr(summary_generator, "_summarize_paragraph", summarize)
    monkeypatch.setattr(summary_generator, "_verify", verify)
    monkeypatch.setattr(summary_generator, "_synthesis", synthesize)

    async def collect_events():
        events = []
        async for event in summary_generator.generate_summary_with_events(
            [
                SourceParagraph("Тема 1", "Текст 1", paragraph_id=1),
                SourceParagraph("Тема 2", "Текст 2", paragraph_id=2),
            ]
        ):
            events.append(event)
            if event.paragraph_id == 2 and event.status == "summarization":
                release_first_extract.set()
        return events

    events = asyncio.run(collect_events())

    assert call_order.index("summarize_2") < call_order.index("extract_done_1")
    assert any(
        event.paragraph_id == 1 and event.status == "summarization" for event in events
    )
