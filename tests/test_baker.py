import asyncio

from app.logics.layout.validator import validate
from app.logics.summary import baker
from app.logics.summary.models import BakedBlock, PlanItem, SourceParagraph, TextFact


def test_bake_prompt_requests_validator_compatible_html_card(monkeypatch):
    captured: dict[str, str] = {}
    expected = BakedBlock(
        plan_item=1,
        text=(
            "<card-title>Причины</card-title>"
            "<card-body><p>Основной факт.</p></card-body>"
        ),
    )

    async def fake_invoke_structured(schema, system_prompt: str, user_prompt: str):
        captured["system"] = system_prompt
        captured["user"] = user_prompt
        return schema(blocks=[expected])

    monkeypatch.setattr(baker, "invoke_structured", fake_invoke_structured)

    result = asyncio.run(
        baker.bake(
            SourceParagraph(title="Тема", text="Исходный текст"),
            [PlanItem(id=1, title="Причины", question="Почему это произошло?")],
            {
                1: [
                    TextFact(
                        type="text",
                        plan_item=1,
                        content="Основной факт.",
                        source_fragment="Основной факт.",
                    )
                ]
            },
        )
    )

    prompt = captured["system"]
    assert result == [expected]
    assert validate(result[0].text)
    assert "ровно одну карточку на каждый пункт плана" in prompt
    assert "<card-title>Короткий заголовок пункта</card-title>" in prompt
    assert "<card-body>Содержимое карточки</card-body>" in prompt
    assert "Не добавляй сведений" in prompt
    assert "Не используй LaTeX и Markdown" in prompt
    assert "div, span" in prompt
