from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from app.logics.summary.baker import bake as bake_cards
from app.logics.summary.cleaner import clean_text
from app.logics.summary.extractor import extract_facts
from app.logics.summary.models import BakedBlock, Fact, PlanItem, SourceParagraph
from app.logics.summary.planner import make_plan
from app.logics.summary.text_baker import bake as bake_text


@dataclass
class SummaryGeneratorEvent:
    status: Literal["cleaning", "planing", "extracting", "baking", "done"]
    is_done: bool
    plan: list[PlanItem] | None = None
    result: list[BakedBlock] | None = None


async def _generate_summary(
    paragraph: SourceParagraph,
    baker: Callable[
        [SourceParagraph, list[PlanItem], dict[int, list[Fact]]],
        Awaitable[list[BakedBlock]],
    ],
) -> AsyncGenerator[SummaryGeneratorEvent]:
    yield SummaryGeneratorEvent("cleaning", False)
    cleaned_paragraph = await clean_text(paragraph)

    yield SummaryGeneratorEvent("planing", False)
    plan = await make_plan(cleaned_paragraph)

    yield SummaryGeneratorEvent("extracting", False, plan=plan)
    facts = await extract_facts(plan, cleaned_paragraph)

    yield SummaryGeneratorEvent("baking", False, plan=plan)
    blocks = await baker(cleaned_paragraph, plan, facts)

    yield SummaryGeneratorEvent("done", True, plan=plan, result=blocks)


async def generate_text_summary(
    paragraph: SourceParagraph,
) -> AsyncGenerator[SummaryGeneratorEvent]:
    """Generate a text report using the shared preparation steps and text baker."""
    async for event in _generate_summary(paragraph, bake_text):
        yield event


async def generate_card_summary(
    paragraph: SourceParagraph,
) -> AsyncGenerator[SummaryGeneratorEvent]:
    """Generate HTML cards using shared preparation steps and the card baker."""
    async for event in _generate_summary(paragraph, bake_cards):
        yield event


async def generate_summary(
    paragraph: SourceParagraph,
) -> AsyncGenerator[SummaryGeneratorEvent]:
    """Backward-compatible alias for the text report workflow."""
    async for event in generate_text_summary(paragraph):
        yield event
