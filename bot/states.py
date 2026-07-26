from aiogram.fsm.state import State, StatesGroup


class AddOperation(StatesGroup):
    waiting_category = State()


class AddIncome(StatesGroup):
    waiting_amount = State()
    waiting_category = State()


class AddLimit(StatesGroup):
    waiting_amount = State()


class AddCategory(StatesGroup):
    waiting_name = State()   # ввод названия новой категории
