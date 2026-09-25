from types import SimpleNamespace

from app.logics.summary_generator import ParagraphAbstractor


class FakeClient:
    def __init__(self, content: str):
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )
        completions = SimpleNamespace(create=lambda **_: response)
        self.chat = SimpleNamespace(completions=completions)


def test_short_summary_is_returned_as_one_block():
    abstractor = ParagraphAbstractor(
        api_key="test",
        client=FakeClient("Короткий конспект."),
    )

    assert abstractor.summarize("Текст параграфа") == ["Короткий конспект."]


def test_only_supported_html_tags_are_preserved():
    generated_text = (
        "<h1>Тема</h1> <em>важно</em> <strong>ключевое</strong> "
        "<s>старое</s> <u>термин</u> <code>x = 1</code> "
        "<pre>пример</pre> <blockquote>цитата</blockquote> <mark>важно</mark> "
        "<a href='https://example.com'>ссылка</a> <script>опасно</script>"
    )
    abstractor = ParagraphAbstractor(
        api_key="test",
        client=FakeClient(generated_text),
    )

    assert abstractor.summarize("Текст параграфа") == [
        "<h1>Тема</h1> <em>важно</em> <strong>ключевое</strong> "
        "<s>старое</s> <u>термин</u> <code>x = 1</code> "
        "<pre>пример</pre> <blockquote>цитата</blockquote> <mark>важно</mark> "
        "ссылка опасно"
    ]


def test_llm_block_markers_preserve_microtopic_boundaries():
    generated_text = (
        "[[BLOCK]] Определение микротемы.\n"
        "[[BLOCK]] Причина и следствие.\n"
        "[[BLOCK]] Пример применения."
    )
    abstractor = ParagraphAbstractor(
        api_key="test",
        client=FakeClient(generated_text),
    )

    assert abstractor.summarize("Текст параграфа") == [
        "Определение микротемы.",
        "Причина и следствие.",
        "Пример применения.",
    ]


def test_long_summary_is_split_into_blocks_up_to_4000_characters():
    generated_text = "Первая тема\n\n" + "Предложение. " * 700 + "\n\nВторая тема"
    abstractor = ParagraphAbstractor(
        api_key="test",
        client=FakeClient(generated_text),
    )

    blocks = abstractor.summarize("Текст параграфа")

    assert len(blocks) > 1
    assert all(0 < len(block) <= 4_000 for block in blocks)
    assert " ".join(" ".join(blocks).split()) == " ".join(generated_text.split())


def test_single_word_longer_than_limit_is_hard_split():
    generated_text = "А" * 8_500
    abstractor = ParagraphAbstractor(
        api_key="test",
        client=FakeClient(generated_text),
    )

    blocks = abstractor.summarize("Текст параграфа")

    assert [len(block) for block in blocks] == [4_000, 4_000, 500]
    assert "".join(blocks) == generated_text
