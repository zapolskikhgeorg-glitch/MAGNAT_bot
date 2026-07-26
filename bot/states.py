from aiogram.fsm.state import State, StatesGroup


class AddOperation(StatesGroup):
    waiting_category = State()   # выбор категории расхода (быстрый ввод)


class AddIncome(StatesGroup):
    waiting_amount = State()     # ввод суммы дохода
    waiting_category = State()   # выбор категории дохода


class AddLimit(StatesGroup):
    waiting_amount = State()     # ввод суммы лимита
