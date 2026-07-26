from aiogram.fsm.state import State, StatesGroup


class AddOperation(StatesGroup):
    waiting_category = State()
