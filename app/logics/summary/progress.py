from typing import ClassVar

from app.logics.summary.models import SourceParagraph
from app.logics.summary.summary_generator import SummaryEvent


class SummaryProgress:
    _PHASE_START: ClassVar[dict[str, tuple[int, str]]] = {
        "extracting": (1, "Извлечение"),
        "summarization": (4, "Конспект"),
        "verifying": (7, "Проверка"),
    }
    _PHASE_COMPLETE: ClassVar[dict[str, int]] = {
        "extracting": 3,
        "summarization": 6,
        "verifying": 9,
    }
    _BAR_WIDTH: ClassVar[int] = 10

    def __init__(self, paragraphs: list[SourceParagraph]) -> None:
        self._paragraph_ids = [
            paragraph.paragraph_id if paragraph.paragraph_id is not None else index + 1
            for index, paragraph in enumerate(paragraphs)
        ]
        self._progress = {paragraph_id: 0 for paragraph_id in self._paragraph_ids}
        self._labels = {
            paragraph_id: "В очереди" for paragraph_id in self._paragraph_ids
        }
        self._phases: dict[int, str] = {}
        self._synthesizing = False

    def handle_event(self, event: SummaryEvent) -> None:
        if event.status == "synthesis":
            self._synthesizing = True
            for paragraph_id in self._paragraph_ids:
                self._progress[paragraph_id] = self._BAR_WIDTH
                self._labels[paragraph_id] = "Готово"
            return

        if event.paragraph_id not in self._progress:
            return
        if event.status == "waiting_for_others":
            phase = self._phases.get(event.paragraph_id)
            if phase is not None:
                self._progress[event.paragraph_id] = self._PHASE_COMPLETE[phase]
                self._labels[event.paragraph_id] = "Ожидание"
            return

        progress, label = self._PHASE_START[event.status]
        self._phases[event.paragraph_id] = event.status
        self._progress[event.paragraph_id] = max(
            self._progress[event.paragraph_id], progress
        )
        self._labels[event.paragraph_id] = label

    def get_status(self) -> str:
        if self._synthesizing:
            lines = ["Собираю итоговый конспект…"]
        else:
            lines = ["Готовлю конспект…"]
        completed = sum(
            progress == self._BAR_WIDTH for progress in self._progress.values()
        )
        lines.append(f"Параграфы: {completed}/{len(self._paragraph_ids)}")

        for index, paragraph_id in enumerate(self._paragraph_ids, start=1):
            filled = self._progress[paragraph_id]
            bar = "▰" * filled + "▱" * (self._BAR_WIDTH - filled)
            line = f"{index:02}. [{bar}]  {self._labels[paragraph_id]}"
            remaining = len(self._paragraph_ids) - index
            if len("\n".join((*lines, line))) > 3700:
                lines.append(f"…и ещё {remaining + 1} параграфов")
                break
            lines.append(line)
        return "\n".join(lines)
