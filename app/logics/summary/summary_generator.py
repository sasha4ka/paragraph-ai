from app.logics.summary.baker import bake
from app.logics.summary.cleaner import clean_text
from app.logics.summary.extractor import extract_facts
from app.logics.summary.models import BakedBlock, SourceParagraph
from app.logics.summary.planner import make_plan


async def generate_summary(paragraph: SourceParagraph) -> list[BakedBlock]:
    cleaned_paragraph = await clean_text(paragraph)
    plan = await make_plan(cleaned_paragraph)
    facts = await extract_facts(plan, cleaned_paragraph)
    blocks = await bake(cleaned_paragraph, plan, facts)
    return blocks
