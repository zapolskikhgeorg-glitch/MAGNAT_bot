import html
import re
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import quote

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.deep_linking import create_start_link
from sqlalchemy import select, delete

from bot.database import get_session
from bot.models import Trip, TripMember, TripExpense, TripPayment, User, generate_invite_code
from bot.utils import get_or_create_user

router = Router()

MAX_MEMBERS = 5
AMOUNT_RE = re.compile(r"^\s*(\d+(?:[.,]\d{1,2})?)\s*(.*)$")


class TripFSM(StatesGroup):
    name = State()
    expense = State()
    payment = State()


def fmt(v) -> str:
    return f"{int(round(float(v))):,}".replace(",", " ")


def esc(s: str) -> str:
    return html.escape(s or "")


def parse_amount(text: str):
    m = AMOUNT_RE.match(text)
    if not m:
        return None
    try:
        amt = Decimal(m.group(1).replace(",", ".")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    except Exception:
        return None
    if amt <= 0:
        return None
    return amt, m.group(2).strip()


# ── Клавиатуры ────────────────────────────────────────────────
def menu_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🏠 Меню", callback_data="menu")
    return b.as_markup()


def cancel_kb(target: str):
    b = InlineKeyboardBuilder()
    b.button(text="◀️ Отмена", callback_data=target)
    return b.as_markup()


def back_trip_kb(tid: int):
    b = InlineKeyboardBuilder()
    b.button(text="◀️ Назад", callback_data=f"trip_open:{tid}")
    b.button(text="🏠 Меню", callback_data="menu")
    b.adjust(1)
    return b.as_markup()


def trip_kb(trip, is_owner: bool):
    b = InlineKeyboardBuilder()
    if not trip.is_archived:
        b.button(text="➕ Добавить трату", callback_data=f"trip_addexp:{trip.id}")
        b.button(text="💸 Закинул частично", callback_data=f"trip_pay:{trip.id}")
        b.button(text="🧮 Посчитаться", callback_data=f"trip_settle:{trip.id}")
        b.button(text="👤 Пригласить участника", callback_data=f"trip_invite:{trip.id}")
        if is_owner:
            b.button(text="📦 В архив", callback_data=f"trip_archive:{trip.id}")
    else:
        b.button(text="🧮 Посчитаться", callback_data=f"trip_settle:{trip.id}")
        if is_owner:
            b.button(text="♻️ Вернуть из архива", callback_data=f"trip_unarchive:{trip.id}")
            b.button(text="🗑 Удалить поездку", callback_data=f"trip_del:{trip.id}")
    b.button(text="◀️ К поездкам", callback_data="splitwise")
    b.adjust(1)
    return b.as_markup()


# ── Вспомогательное ───────────────────────────────────────────
async def _members(session, trip_id: int):
    res = await session.execute(
        select(User)
        .join(TripMember, TripMember.user_id == User.id)
        .where(TripMember.trip_id == trip_id)
        .order_by(TripMember.id)
    )
    return list(res.scalars().all())


async def _is_member(session, trip_id: int, user_id: int) -> bool:
    res = await session.execute(
        select(TripMember).where(
            TripMember.trip_id == trip_id, TripMember.user_id == user_id
        )
    )
    return res.scalar_one_or_none() is not None


async def _home_view(session, user_id: int):
    res = await session.execute(
        select(Trip)
        .join(TripMember, TripMember.trip_id == Trip.id)
        .where(TripMember.user_id == user_id)
        .order_by(Trip.is_archived, Trip.id)
    )
    trips = list(res.scalars().all())

    lines = ["🧾 Splitwise — поездки", ""]
    if not trips:
        lines.append("У тебя пока нет поездок. Создай первую 👇")
    else:
        lines.append("Твои поездки:")
        for t in trips:
            if t.is_archived:
                lines.append(f"• <s>{esc(t.name)}</s> ✅ закрыта")
            else:
                lines.append(f"• {esc(t.name)}")

    b = InlineKeyboardBuilder()
    for t in trips:
        prefix = "✅ " if t.is_archived else "🧾 "
        b.button(text=f"{prefix}{t.name}", callback_data=f"trip_open:{t.id}")
    b.button(text="➕ Создать поездку", callback_data="spl_create")
    b.button(text="🏠 Меню", callback_data="menu")
    b.adjust(1)
    return "\n".join(lines), b.as_markup()


async def _trip_text(session, trip):
    members = await _members(session, trip.id)
    res = await session.execute(
        select(TripExpense).where(TripExpense.trip_id == trip.id)
    )
    expenses = list(res.scalars().all())
    total = sum(float(e.amount) for e in expenses)

    lines = [f"🧾 {esc(trip.name)}"]
    if trip.is_archived:
        lines.append("📦 В архиве (поездка закрыта)")
    lines.append("")
    names = ", ".join(esc(m.first_name or "Без имени") for m in members)
    lines.append(f"Участники ({len(members)}/{MAX_MEMBERS}): {names}")
    lines.append("")
    lines.append(f"Всего потрачено: {fmt(total)} ₽")
    return "\n".join(lines)


def _settlements(balance: dict):
    creditors = sorted(([i, b] for i, b in balance.items() if b > 0.5), key=lambda x: -x[1])
    debtors = sorted(([i, -b] for i, b in balance.items() if b < -0.5), key=lambda x: -x[1])
    out = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        d, c = debtors[i], creditors[j]
        pay = min(d[1], c[1])
        amt = int(round(pay))
        if amt > 0:
            out.append((d[0], c[0], amt))
        d[1] -= pay
        c[1] -= pay
        if d[1] <= 0.5:
            i += 1
        if c[1] <= 0.5:
            j += 1
    return out


async def _settle_text(session, trip):
    members = await _members(session, trip.id)
    names = {m.id: (m.first_name or "Без имени") for m in members}
    ids = [m.id for m in members]

    exp_res = await session.execute(
        select(TripExpense).where(TripExpense.trip_id == trip.id)
    )
    expenses = list(exp_res.scalars().all())
    pay_res = await session.execute(
        select(TripPayment).where(TripPayment.trip_id == trip.id)
    )
    payments = list(pay_res.scalars().all())

    paid = {i: 0.0 for i in ids}
    for e in expenses:
        if e.user_id in paid:
            paid[e.user_id] += float(e.amount)

    total = sum(paid.values())
    n = len(ids)
    share = total / n if n else 0
    balance = {i: paid[i] - share for i in ids}
    for p in payments:
        if p.from_user_id in balance:
            balance[p.from_user_id] += float(p.amount)
        if p.to_user_id in balance:
            balance[p.to_user_id] -= float(p.amount)

    transfers = _settlements(dict(balance))

    lines = [f"🧮 Расчёт: {esc(trip.name)}", ""]
    lines.append(f"Всего потрачено: {fmt(total)} ₽, по {fmt(share)} ₽ на каждого.")
    lines.append("")
    lines.append("Потратил каждый:")
    for i in ids:
        lines.append(f"• {esc(names[i])}: {fmt(paid[i])} ₽")

    if payments:
        lines.append("")
        lines.append("Уже переведено:")
        for p in payments:
            frm = esc(names.get(p.from_user_id, "?"))
            to = esc(names.get(p.to_user_id, "?"))
            lines.append(f"• {frm} → {to}: {fmt(p.amount)} ₽")

    lines.append("")
    if not transfers:
        lines.append("Все в расчёте — никто никому не должен ✅")
    else:
        lines.append("Осталось перевести:")
        for f, t, a in transfers:
            lines.append(f"• {esc(names[f])} → {esc(names[t])}: {fmt(a)} ₽")
    return "\n".join(lines)


# ── Главный экран ─────────────────────────────────────────────
@router.callback_query(F.data == "splitwise")
async def sw_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with get_session() as session:
        user = await get_or_create_user(
            session, callback.from_user.id, callback.from_user.first_name or ""
        )
        text, kb = await _home_view(session, user.id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# ── Создание поездки ──────────────────────────────────────────
@router.callback_query(F.data == "spl_create")
async def spl_create(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TripFSM.name)
    await callback.message.edit_text(
        "🧾 Новая поездка\n\nВведи название (например: Сочи, июль):",
        reply_markup=cancel_kb("splitwise"),
    )
    await callback.answer()


@router.message(TripFSM.name, F.text, ~F.text.startswith("/"))
async def spl_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()[:100]
    async with get_session() as session:
        user = await get_or_create_user(
            session, message.from_user.id, message.from_user.first_name or ""
        )
        trip = Trip(owner_id=user.id, name=name, invite_code=generate_invite_code())
        session.add(trip)
        await session.commit()
        await session.refresh(trip)
        session.add(TripMember(trip_id=trip.id, user_id=user.id))
        await session.commit()
        text = await _trip_text(session, trip)

    await state.clear()
    await message.answer(
        text + "\n\nТеперь пригласи участников кнопкой ниже 👇",
        reply_markup=trip_kb(trip, True),
        parse_mode="HTML",
    )


# ── Открыть поездку ───────────────────────────────────────────
@router.callback_query(F.data.startswith("trip_open:"))
async def trip_open(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    tid = int(callback.data.split(":")[1])
    async with get_session() as session:
        user = await get_or_create_user(
            session, callback.from_user.id, callback.from_user.first_name or ""
        )
        trip = await session.get(Trip, tid)
        if trip is None or not await _is_member(session, tid, user.id):
            await callback.answer("Поездка не найдена", show_alert=True)
            return
        text = await _trip_text(session, trip)
        is_owner = trip.owner_id == user.id
    await callback.message.edit_text(text, reply_markup=trip_kb(trip, is_owner), parse_mode="HTML")
    await callback.answer()


# ── Пригласить ────────────────────────────────────────────────
@router.callback_query(F.data.startswith("trip_invite:"))
async def trip_invite(callback: CallbackQuery) -> None:
    tid = int(callback.data.split(":")[1])
    async with get_session() as session:
        user = await get_or_create_user(
            session, callback.from_user.id, callback.from_user.first_name or ""
        )
        trip = await session.get(Trip, tid)
        if trip is None or not await _is_member(session, tid, user.id):
            await callback.answer("Поездка не найдена", show_alert=True)
            return
        members = await _members(session, tid)
        code = trip.invite_code
        trip_name = trip.name

    if len(members) >= MAX_MEMBERS:
        await callback.message.edit_text(
            "👥 В поездке уже 5 участников — больше добавить нельзя.",
            reply_markup=back_trip_kb(tid),
        )
        await callback.answer()
        return

    me = await callback.bot.get_me()
    link = await create_start_link(callback.bot, f"spl_{code}", encode=False)
    share_text = (
        f"Приглашаю тебя в поездку «{trip_name}» в боте @{me.username} — "
        f"считаем общие расходы вместе. Жми ссылку!"
    )
    share_url = f"https://t.me/share/url?url={quote(link)}&text={quote(share_text)}"

    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Выбрать, кому отправить", url=share_url)
    kb.button(text="◀️ Назад", callback_data=f"trip_open:{tid}")
    kb.adjust(1)

    await callback.message.edit_text(
        "🔗 Приглашение готово!\n\n"
        "Нажми кнопку ниже — откроется поиск по контактам Telegram. "
        "Выбери человека, и приглашение уйдёт ему в личку.",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


# ── Приём / отклонение приглашения ────────────────────────────
@router.callback_query(F.data.startswith("trip_accept:"))
async def trip_accept(callback: CallbackQuery) -> None:
    code = callback.data.split(":", 1)[1]
    async with get_session() as session:
        user = await get_or_create_user(
            session, callback.from_user.id, callback.from_user.first_name or ""
        )
        res = await session.execute(select(Trip).where(Trip.invite_code == code))
        trip = res.scalar_one_or_none()

        if trip is None:
            await callback.message.edit_text(
                "❌ Приглашение недействительно.", reply_markup=menu_kb()
            )
            await callback.answer()
            return
        if trip.is_archived:
            await callback.message.edit_text(
                "Эта поездка уже закрыта.", reply_markup=menu_kb()
            )
            await callback.answer()
            return
        if await _is_member(session, trip.id, user.id):
            text = await _trip_text(session, trip)
            await callback.message.edit_text(
                "Ты уже участник этой поездки 🙂\n\n" + text,
                reply_markup=trip_kb(trip, trip.owner_id == user.id),
                parse_mode="HTML",
            )
            await callback.answer()
            return
        members = await _members(session, trip.id)
        if len(members) >= MAX_MEMBERS:
            await callback.message.edit_text(
                "👥 В этой поездке уже 5 участников — присоединиться нельзя.",
                reply_markup=menu_kb(),
            )
            await callback.answer()
            return

        session.add(TripMember(trip_id=trip.id, user_id=user.id))
        await session.commit()
        text = await _trip_text(session, trip)

    await callback.message.edit_text(
        "✅ Ты присоединился к поездке!\n\n" + text,
        reply_markup=trip_kb(trip, False),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "trip_decline")
async def trip_decline(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Приглашение отклонено.", reply_markup=menu_kb())
    await callback.answer()


# ── Добавить трату (за себя) ──────────────────────────────────
@router.callback_query(F.data.startswith("trip_addexp:"))
async def trip_addexp(callback: CallbackQuery, state: FSMContext) -> None:
    tid = int(callback.data.split(":")[1])
    await state.update_data(trip_id=tid)
    await state.set_state(TripFSM.expense)
    await callback.message.edit_text(
        "Сколько ты потратил и на что? (например: 10000 квартира):",
        reply_markup=cancel_kb(f"trip_open:{tid}"),
    )
    await callback.answer()


@router.message(TripFSM.expense, F.text, ~F.text.startswith("/"))
async def trip_expense_amount(message: Message, state: FSMContext) -> None:
    parsed = parse_amount(message.text)
    if parsed is None:
        await message.answer("Не понял сумму 🤔 Например: 10000 квартира")
        return
    amount, desc = parsed
    data = await state.get_data()
    tid = int(data["trip_id"])

    async with get_session() as session:
        user = await get_or_create_user(
            session, message.from_user.id, message.from_user.first_name or ""
        )
        session.add(
            TripExpense(trip_id=tid, user_id=user.id, amount=amount, description=desc)
        )
        await session.commit()
        trip = await session.get(Trip, tid)
        text = await _trip_text(session, trip)
        is_owner = trip.owner_id == user.id

    await state.clear()
    await message.answer(text, reply_markup=trip_kb(trip, is_owner), parse_mode="HTML")


# ── Закинул частично (перевод) ────────────────────────────────
@router.callback_query(F.data.startswith("trip_pay:"))
async def trip_pay(callback: CallbackQuery) -> None:
    tid = int(callback.data.split(":")[1])
    async with get_session() as session:
        user = await get_or_create_user(
            session, callback.from_user.id, callback.from_user.first_name or ""
        )
        members = await _members(session, tid)
    others = [m for m in members if m.id != user.id]
    if not others:
        await callback.answer("В поездке пока только ты", show_alert=True)
        return

    b = InlineKeyboardBuilder()
    for m in others:
        b.button(text=m.first_name or "Без имени", callback_data=f"trip_payto:{tid}:{m.id}")
    b.adjust(2)
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data=f"trip_open:{tid}"))
    await callback.message.edit_text("Кому ты перевёл деньги?", reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("trip_payto:"))
async def trip_payto(callback: CallbackQuery, state: FSMContext) -> None:
    _, tid, uid = callback.data.split(":")
    await state.update_data(trip_id=int(tid), to_uid=int(uid))
    await state.set_state(TripFSM.payment)
    async with get_session() as session:
        to_user = await session.get(User, int(uid))
    name = to_user.first_name if to_user else "участнику"
    await callback.message.edit_text(
        f"Сколько ты перевёл {name}? (например: 2000):",
        reply_markup=cancel_kb(f"trip_open:{tid}"),
    )
    await callback.answer()


@router.message(TripFSM.payment, F.text, ~F.text.startswith("/"))
async def trip_payment_amount(message: Message, state: FSMContext) -> None:
    parsed = parse_amount(message.text)
    if parsed is None:
        await message.answer("Не понял сумму 🤔 Введи число, например: 2000")
        return
    amount, _ = parsed
    data = await state.get_data()
    tid = int(data["trip_id"])
    to_uid = int(data["to_uid"])

    async with get_session() as session:
        user = await get_or_create_user(
            session, message.from_user.id, message.from_user.first_name or ""
        )
        session.add(
            TripPayment(
                trip_id=tid, from_user_id=user.id, to_user_id=to_uid, amount=amount
            )
        )
        await session.commit()
        trip = await session.get(Trip, tid)
        text = await _settle_text(session, trip)

    await state.clear()
    await message.answer(text, reply_markup=back_trip_kb(tid), parse_mode="HTML")


# ── Посчитаться ───────────────────────────────────────────────
@router.callback_query(F.data.startswith("trip_settle:"))
async def trip_settle(callback: CallbackQuery) -> None:
    tid = int(callback.data.split(":")[1])
    async with get_session() as session:
        trip = await session.get(Trip, tid)
        if trip is None:
            await callback.answer("Поездка не найдена", show_alert=True)
            return
        text = await _settle_text(session, trip)
    await callback.message.edit_text(text, reply_markup=back_trip_kb(tid), parse_mode="HTML")
    await callback.answer()


# ── Архив / возврат / удаление (только владелец) ──────────────
@router.callback_query(F.data.startswith("trip_archive:"))
async def trip_archive(callback: CallbackQuery) -> None:
    tid = int(callback.data.split(":")[1])
    async with get_session() as session:
        user = await get_or_create_user(
            session, callback.from_user.id, callback.from_user.first_name or ""
        )
        trip = await session.get(Trip, tid)
        if trip is None or trip.owner_id != user.id:
            await callback.answer("Только создатель может архивировать", show_alert=True)
            return
        trip.is_archived = True
        await session.commit()
        text, kb = await _home_view(session, user.id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer("Поездка отправлена в архив")


@router.callback_query(F.data.startswith("trip_unarchive:"))
async def trip_unarchive(callback: CallbackQuery) -> None:
    tid = int(callback.data.split(":")[1])
    async with get_session() as session:
        user = await get_or_create_user(
            session, callback.from_user.id, callback.from_user.first_name or ""
        )
        trip = await session.get(Trip, tid)
        if trip is None or trip.owner_id != user.id:
            await callback.answer("Только создатель может вернуть из архива", show_alert=True)
            return
        trip.is_archived = False
        await session.commit()
        text = await _trip_text(session, trip)
    await callback.message.edit_text(text, reply_markup=trip_kb(trip, True), parse_mode="HTML")
    await callback.answer("Поездка снова активна")


@router.callback_query(F.data.startswith("trip_del:"))
async def trip_del(callback: CallbackQuery) -> None:
    tid = int(callback.data.split(":")[1])
    b = InlineKeyboardBuilder()
    b.button(text="🗑 Да, удалить", callback_data=f"trip_delok:{tid}")
    b.button(text="◀️ Отмена", callback_data=f"trip_open:{tid}")
    b.adjust(1)
    await callback.message.edit_text(
        "🗑 Удалить поездку со всеми тратами и переводами?",
        reply_markup=b.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("trip_delok:"))
async def trip_delok(callback: CallbackQuery, state: FSMContext) -> None:
    tid = int(callback.data.split(":")[1])
    async with get_session() as session:
        user = await get_or_create_user(
            session, callback.from_user.id, callback.from_user.first_name or ""
        )
        trip = await session.get(Trip, tid)
        if trip is None or trip.owner_id != user.id:
            await callback.answer("Только создатель может удалить", show_alert=True)
            return
        await session.execute(delete(TripPayment).where(TripPayment.trip_id == tid))
        await session.execute(delete(TripExpense).where(TripExpense.trip_id == tid))
        await session.execute(delete(TripMember).where(TripMember.trip_id == tid))
        await session.execute(delete(Trip).where(Trip.id == tid))
        await session.commit()
        text, kb = await _home_view(session, user.id)

    await state.clear()
    await callback.message.edit_text("✅ Поездка удалена.\n\n" + text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()
