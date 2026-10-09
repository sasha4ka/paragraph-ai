from app.logics.summary.models import SourceParagraph
from app.logics.summary.progress import SummaryProgress
from app.logics.summary.summary_generator import SummaryEvent


def test_summary_progress_shows_indexed_bars_without_paragraph_names():
    progress = SummaryProgress([SourceParagraph("Тема 1", "Текст", paragraph_id=12)])

    progress.handle_event(SummaryEvent(12, "Тема 1", "extracting"))
    status = progress.get_status()
    assert "01. [▰▱▱▱▱▱▱▱▱▱]  Извлечение" in status
    assert "Тема 1" not in status

    progress.handle_event(SummaryEvent(12, "Тема 1", "waiting_for_others"))
    assert "01. [▰▰▰▱▱▱▱▱▱▱]  Ожидание" in progress.get_status()

    progress.handle_event(SummaryEvent(12, "Тема 1", "summarization"))
    assert "01. [▰▰▰▰▱▱▱▱▱▱]  Конспект" in progress.get_status()

    progress.handle_event(SummaryEvent(0, "Итоговый конспект", "synthesis"))
    status = progress.get_status()
    assert status.startswith("Собираю итоговый конспект…")
    assert "Параграфы: 1/1" in status
    assert "01. [▰▰▰▰▰▰▰▰▰▰]  Готово" in status


def test_summary_progress_truncates_long_status_to_message_limit():
    progress = SummaryProgress(
        [
            SourceParagraph(f"Тема {index}", "Текст", paragraph_id=index)
            for index in range(200)
        ]
    )

    assert len(progress.get_status()) <= 3800
    assert "…и ещё" in progress.get_status()
