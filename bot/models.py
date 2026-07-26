import secrets
from datetime import datetime, date
from sqlalchemy import String, BigInteger, Numeric, Date, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(255), default="")
    family_id: Mapped[int | None] = mapped_column(ForeignKey("families.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Family(Base):
    __tablename__ = "families"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), default="Семейный бюджет")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    invite_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def generate_invite_code() -> str:
    return secrets.token_urlsafe(9)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    icon: Mapped[str] = mapped_column(String(10), default="")
    type: Mapped[str] = mapped_column(String(10))  # "expense" или "income"
    is_default: Mapped[bool] = mapped_column(Boolean, default=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Operation(Base):
    __tablename__ = "operations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(String(10))  # "expense" или "income"
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    raw_text: Mapped[str] = mapped_column(String(500), default="")
    operation_date: Mapped[date] = mapped_column(Date, default=date.today)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CategoryLimit(Base):
    __tablename__ = "category_limits"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    limit_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# Базовые категории — создаются/досоздаются при запуске бота.
DEFAULT_EXPENSE_CATEGORIES = [
    ("Продукты", "🛒"),
    ("Жильё", "🏠"),
    ("Транспорт", "🚗"),
    ("Кафе и рестораны", "🍕"),
    ("Здоровье", "💊"),
    ("Развлечения", "🎮"),
    ("Одежда и обувь", "👕"),
    ("Связь", "📱"),
    ("Коммуналка", "💡"),
    ("Образование", "🎓"),
    ("Другое", "📦"),
]
DEFAULT_INCOME_CATEGORIES = [
    ("Зарплата", "💼"),
    ("Фриланс", "💻"),
    ("Подработка", "🤝"),
    ("Инвестиции", "📈"),
    ("Подарки/Бонусы", "🎁"),
    ("Другое", "💰"),
]
