import asyncio
from importlib import import_module
from types import SimpleNamespace

from app.states import Summarize

router = import_module("app.handlers.summarize.router")


def test_quiz_stores_answers_checks_result_and_opens_follow_up(monkeypatch):
    questions = [
        {"id": "B2", "question": "Формула?", "options": ["A", "B", "C", "D"], "correct_option": 0},
        {"id": "C3", "question": "Объясните почему.", "reference_answer": "Эталон"},
    ]
    data = {"quiz_test": {"title": "Химия", "questions": questions}, "quiz_answers": {}}
    sent = []
    states = []

    async def get_data():
        return data

    async def update_data(**kwargs):
        data.update(kwargs)

    async def set_state(state):
        states.append(state)

    async def answer(**kwargs):
        sent.append(kwargs["text"])

    class Checker:
        def __init__(self, test, answers):
            assert answers == {"B2": 1, "C3": "Мой ответ"}

        async def check_async(self):
            return {
                "total_score": 0,
                "max_score": 5,
                "results": [{"id": "B2", "score": 0, "max_score": 2, "feedback": "Ошибка"}],
            }

    class Tutor:
        def __init__(self, messages):
            assert messages[-1]["content"] == "Объясни ошибки"
            assert '"total_score": 0' in messages[0]["content"]

        async def respond_async(self):
            return "Разбор ошибок"

    monkeypatch.setattr(router, "AnswerChecker", Checker)
    monkeypatch.setattr(router, "Communication", Tutor)
    context = SimpleNamespace(get_data=get_data, update_data=update_data, set_state=set_state)
    body = SimpleNamespace(text="7")
    event = SimpleNamespace(message=SimpleNamespace(body=body, answer=answer))

    async def run():
        await router._send_quiz_question(event, questions[0])
        await router.answer_quiz_question(event, context)
        assert not data["quiz_answers"]
        body.text = "2"
        await router.answer_quiz_question(event, context)
        body.text = "Мой ответ"
        await router.answer_quiz_question(event, context)
        assert states[-1] == Summarize.quiz_review
        body.text = "Объясни ошибки"
        await router.review_quiz(event, context)

    asyncio.run(run())
    assert "1. A" in sent[0]
    assert "Введите номер варианта" in sent[1]
    assert "C3. Объясните почему." in sent[2]
    assert "Эталон" not in sent[2]
    assert "0 из 5 баллов." in sent[3]
    assert sent[-1] == "Разбор ошибок"
