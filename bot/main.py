import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.config import BOT_TOKEN
from bot.database import init_db
from bot.handlers import (
    start,
    menu,
    expense,
    limits,
    categories,
    search,
    export,
    # family,
)

logging.basicConfig(level=logging.INFO)


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать / главное меню"),
        BotCommand(command="menu", description="Главное меню"),
    ])


async def main() -> None:
    await init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(start.router)
    dp.include_router(search.router)
    dp.include_router(export.router)
    # dp.include_router(family.router)
    dp.include_router(menu.router)
    dp.include_router(expense.router)
    dp.include_router(limits.router)
    dp.include_router(categories.router)
    await set_commands(bot)
    logging.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
