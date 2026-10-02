from maxapi.context import State, StatesGroup


class ManageBooks(StatesGroup):
    main_menu = State()
    upload_book = State()
    select_book_name = State()
    processing_book = State()
    select_for_delete = State()


class Summarize(StatesGroup):
    select_book = State()
    select_paragraphs = State()
    chat_mode = State()


class Feedback(StatesGroup):
    enter_feedback = State()
    enter_a_name = State()
    thanks = State()
