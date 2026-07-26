import os

# Токен бота — берётся из переменной окружения BOT_TOKEN.
# На Railway это задаётся в разделе Variables, а не прямо в коде —
# так токен не попадает в открытый код на GitHub.
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Адрес базы данных PostgreSQL — тоже из переменной окружения.
# Railway подставит его автоматически, когда мы подключим базу данных.
DATABASE_URL = os.getenv("DATABASE_URL", "")

if not BOT_TOKEN:
    raise RuntimeError(
        "Не найден BOT_TOKEN. Добавьте его в переменные окружения (Railway → Variables)."
    )

if not DATABASE_URL:
    raise RuntimeError(
        "Не найден DATABASE_URL. Подключите PostgreSQL в Railway — переменная появится сама."
    )

# Railway отдаёт адрес БД в формате postgresql://..., но библиотека,
# с которой мы работаем (asyncpg), ожидает postgresql+asyncpg://...
# Подменяем префикс, чтобы всё работало без ручных правок.
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
