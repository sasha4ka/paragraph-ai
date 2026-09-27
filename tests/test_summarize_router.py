from app.handlers.summarize.router import _split_message


def test_summary_is_split_without_losing_content_after_3900_characters():
    summary = "x" * 4000

    chunks = _split_message(summary)

    assert len(chunks) == 2
    assert all(len(chunk) <= 3900 for chunk in chunks)
    assert "".join(chunks) == summary


def test_summary_splits_on_line_boundaries_when_possible():
    summary = "A" * 2000 + "\n" + "B" * 2000

    chunks = _split_message(summary)

    assert chunks == ["A" * 2000, "B" * 2000]
