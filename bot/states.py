from aiogram.fsm.state import State, StatesGroup


class AddOperation(StatesGroup):
    waiting_type = State()       # выбор Расход / Доход
    waiting_category = State()   # выбор категории


class AddLimit(StatesGroup):
    waiting_amount = State()     # ввод суммы лимита
