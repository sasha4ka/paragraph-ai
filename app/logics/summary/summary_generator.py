from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Literal

from app.logics.summary.baker import bake
from app.logics.summary.cleaner import clean_text
from app.logics.summary.extractor import extract_facts
from app.logics.summary.models import BakedBlock, PlanItem, SourceParagraph
from app.logics.summary.planner import make_plan


@dataclass
class SummaryGeneratorEvent:
    status: Literal["cleaning", "planing", "extracting", "baking", "done"]
    is_done: bool
    plan: list[PlanItem] | None = None
    result: list[BakedBlock] | None = None


async def generate_summary(
    paragraph: SourceParagraph,
) -> AsyncGenerator[SummaryGeneratorEvent]:
    yield SummaryGeneratorEvent("cleaning", False)
    cleaned_paragraph = await clean_text(paragraph)

    yield SummaryGeneratorEvent("planing", False)
    plan = await make_plan(cleaned_paragraph)

    yield SummaryGeneratorEvent("extracting", False, plan=plan)
    facts = await extract_facts(plan, cleaned_paragraph)

    yield SummaryGeneratorEvent("baking", False, plan=plan)
    blocks = await bake(cleaned_paragraph, plan, facts)

    yield SummaryGeneratorEvent("done", True, plan=plan, result=blocks)
