from app.logics.summary.models import SourceParagraph
from app.openai import invoke_model


async def clean_text(paragraph: SourceParagraph) -> SourceParagraph:
    system_prompt = """\
Тебе необходимо очистить текст от артефактов сканирования. К ним относятся:
1. Колонтитулы
2. Колонцифры
3. Сноски и примечания
4. Пропуски букв, лишние пробелы или переносы строк
5. Смешанные несколько колонок текста
Правила очищения:
1. Не изменяй исходный текст параграфа (только исправления лишних пробелов или пропущенных букв)
"""
    user_prompt = f'Текст параграфа: "{paragraph.text}"'
    cleaned_text = await invoke_model(system_prompt, user_prompt)

    return SourceParagraph(paragraph.title, cleaned_text)
