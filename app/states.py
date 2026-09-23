from maxapi.context import State, StatesGroup


class ManageBooks(StatesGroup):
    main_menu = State()
    upload_book = State()
    ask_book_name = State()
    select_for_delete = State()
