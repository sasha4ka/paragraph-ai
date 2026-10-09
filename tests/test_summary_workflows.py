import asyncio

from app.logics.summary import summary_generator
from app.logics.summary.models import BakedBlock, SourceParagraph


def test_text_and_card_workflows_share_preparation_but_use_separate_bakers(
    monkeypatch,
):
    calls: list[str] = []
    text_block = BakedBlock(plan_item=1, text="text output")
    card_block = BakedBlock(
        plan_item=1,
        text=(
            "<card-title>Title</card-title><card-body><p>Card output</p></card-body>"
        ),
    )

    async def clean(paragraph):
        calls.append("clean")
        return paragraph

    async def plan(paragraph):
        calls.append("plan")
        return []

    async def extract(items, paragraph):
        calls.append("extract")
        return {}

    async def bake_text(paragraph, items, facts):
        calls.append("text-baker")
        return [text_block]

    async def bake_cards(paragraph, items, facts):
        calls.append("card-baker")
        return [card_block]

    monkeypatch.setattr(summary_generator, "clean_text", clean)
    monkeypatch.setattr(summary_generator, "make_plan", plan)
    monkeypatch.setattr(summary_generator, "extract_facts", extract)
    monkeypatch.setattr(summary_generator, "bake_text", bake_text)
    monkeypatch.setattr(summary_generator, "bake_cards", bake_cards)

    async def collect(generator):
        return [event async for event in generator(SourceParagraph("Title", "Text"))]

    text_events = asyncio.run(collect(summary_generator.generate_text_summary))
    assert text_events[-1].result == [text_block]
    assert calls == ["clean", "plan", "extract", "text-baker"]

    calls.clear()
    card_events = asyncio.run(collect(summary_generator.generate_card_summary))
    assert card_events[-1].result == [card_block]
    assert calls == ["clean", "plan", "extract", "card-baker"]
