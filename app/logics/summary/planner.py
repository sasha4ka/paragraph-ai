from openai import BaseModel

from app.logics.summary.models import SourceParagraph
from app.models import PlanItem
from app.openai import invoke_structured


class PlannerResult(BaseModel):
    items: list[PlanItem]


async def make_plan(paragraph: SourceParagraph) -> list[PlanItem]:
    system_message = """\
Тебе необходимо разбить текст приведенного параграфа на пункты для устного ответа.
Правила для разбития:
1. Предпочтительно опираться на нумерацию приведенного текста.
2. Если в тексте отсутствует нумерация, разбей его на пункты сам
3. Число пунктов плана плана: 3-7
4. Для каждого пункта плана необходимо указать вопрос, на который он отвечает\
"""
    user_message = f"""\
Название параграфа: {paragraph.title}
Текст параграфа: "{paragraph.text}"\
"""
    result = await invoke_structured(PlannerResult, system_message, user_message)
    return result.items
