from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.deep_linking import create_start_link
from sqlalchemy import select

from bot.database import get_session
from bot.keyboards import (
    family_menu_keyboard,
    family_menu_no_family_keyboard,
    family_leave_confirm_keyboard,
    back_to_menu_keyboard,
)
from bot.models import User, Family, generate_invite_code

router = Router()


async def get_or_create_user(session, tg_user) -> User:
    result = await session.execute(
        select(User).where(User.telegram_id == tg_user.id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(telegram_id=tg_user.id, first_name=tg_user.first_name or "")
        session.add(user)
        await session.flush()
    return user


async def render_family_menu(session, user: User):
    """Возвращает (текст, клавиатура) главного экрана семьи."""
    if user.family_id is None:
        text = (
            "👨‍👩‍👧 Семейный бюджет\n\n"
            "Объедини расходы и доходы с близкими — вся статистика станет общей.\n\n"
            "Создай семейный бюджет и пригласи участников по ссылке."
        )
        return text, family_menu_no_family_keyboard()

    fam = await session.get(Family, user.family_id)
    members_result = await session.execute(
        select(User).where(User.family_id == user.family_id)
    )
    members = members_result.scalars().all()

    lines = [f"👨‍👩‍👧 {fam.name}", ""]
    lines.append(f"Участников: {len(members)}")
    for m in members:
        crown = " 👑" if m.id == fam.owner_id else ""
        lines.append(f"• {m.first_name or 'Без имени'}{crown}")
    lines.append("")
    lines.append("Ваши расходы и доходы считаются вместе.")
    return "\n".join(lines), family_menu_keyboard()


# ===== Главный экран семьи =====
@router.callback_query(F.data == "family")
async def family_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with get_session() as session:
        user = await get_or_create_user(session, callback.from_user)
        text, kb = await render_family_menu(session, user)
        await session.commit()
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ===== Создать семью =====
@router.callback_query(F.data == "family_create")
async def family_create(callback: CallbackQuery) -> None:
    async with get_session() as session:
        user = await get_or_create_user(session, callback.from_user)
        if user.family_id is not None:
            await callback.answer("Ты уже в семье", show_alert=True)
            return
        fam = Family(owner_id=user.id, invite_code=generate_invite_code())
        session.add(fam)
        await session.flush()
        user.family_id = fam.id
        await session.commit()

    await callback.answer("✅ Семейный бюджет создан!")
    async with get_session() as session:
        user = await get_or_create_user(session, callback.from_user)
        text, kb = await render_family_menu(session, user)
        await session.commit()
    await callback.message.edit_text(text, reply_markup=kb)


# ===== Пригласить (ссылка) =====
@router.callback_query(F.data == "family_invite")
async def family_invite(callback: CallbackQuery) -> None:
    async with get_session() as session:
        user = await get_or_create_user(session, callback.from_user)
        if user.family_id is None:
            await callback.answer("Сначала создай семью", show_alert=True)
            return
        fam = await session.get(Family, user.family_id)
        code = fam.invite_code
        await session.commit()

    link = await create_start_link(callback.bot, f"inv_{code}", encode=False)
    text = (
        "➕ Приглашение участника\n\n"
        "Отправь эту ссылку тому, кого хочешь добавить в семейный бюджет:\n\n"
        f"{link}\n\n"
        "Он перейдёт по ссылке и подтвердит присоединение."
    )
    await callback.message.edit_text(text, reply_markup=family_menu_keyboard())
    await callback.answer()


# ===== Участники =====
@router.callback_query(F.data == "family_members")
async def family_members(callback: CallbackQuery) -> None:
    async with get_session() as session:
        user = await get_or_create_user(session, callback.from_user)
        if user.family_id is None:
            await callback.answer("Ты не в семье", show_alert=True)
            return
        fam = await session.get(Family, user.family_id)
        members_result = await session.execute(
            select(User).where(User.family_id == user.family_id)
        )
        members = members_result.scalars().all()
        await session.commit()

    lines = ["👥 Участники семьи", ""]
    for m in members:
        crown = " 👑 (создатель)" if m.id == fam.owner_id else ""
        lines.append(f"• {m.first_name or 'Без имени'}{crown}")
    await callback.message.edit_text("\n".join(lines), reply_markup=family_menu_keyboard())
    await callback.answer()


# ===== Выход из семьи =====
@router.callback_query(F.data == "family_leave")
async def family_leave(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "🚪 Выйти из семьи?\n\n"
        "Твои операции останутся у тебя, но перестанут учитываться в общем бюджете.",
        reply_markup=family_leave_confirm_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "family_leave_confirm")
async def family_leave_confirm(callback: CallbackQuery) -> None:
    async with get_session() as session:
        user = await get_or_create_user(session, callback.from_user)
        if user.family_id is not None:
            fam = await session.get(Family, user.family_id)
            was_owner = fam and fam.owner_id == user.id
            family_id = user.family_id
            user.family_id = None
            await session.flush()

            if was_owner and fam:
                rest = await session.execute(
                    select(User).where(User.family_id == family_id)
                )
                rest_users = rest.scalars().all()
                if rest_users:
                    fam.owner_id = rest_users[0].id
                else:
                    await session.delete(fam)
        await session.commit()

    await callback.answer("Ты вышел из семьи")
    async with get_session() as session:
        user = await get_or_create_user(session, callback.from_user)
        text, kb = await render_family_menu(session, user)
        await session.commit()
    await callback.message.edit_text(text, reply_markup=kb)


# ===== Приём приглашения (кнопка после ссылки) =====
@router.callback_query(F.data.startswith("family_accept:"))
async def family_accept(callback: CallbackQuery) -> None:
    code = callback.data.split(":", 1)[1]
    async with get_session() as session:
        user = await get_or_create_user(session, callback.from_user)
        fam_result = await session.execute(
            select(Family).where(Family.invite_code == code)
        )
        fam = fam_result.scalar_one_or_none()

        if fam is None:
            await session.commit()
            await callback.message.edit_text(
                "❌ Приглашение недействительно или устарело.",
                reply_markup=back_to_menu_keyboard(),
            )
            await callback.answer()
            return

        if user.family_id == fam.id:
            await callback.answer("Ты уже в этой семье", show_alert=True)
            return

        user.family_id = fam.id
        owner = await session.get(User, fam.owner_id)
        owner_name = owner.first_name if owner and owner.first_name else ""
        await session.commit()

    text = (
        f"✅ Ты присоединился к семейному бюджету {owner_name}!\n\n"
        "Теперь ваши расходы учитываются вместе."
    )
    await callback.message.edit_text(text, reply_markup=back_to_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "family_decline")
async def family_decline(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "Приглашение отклонено.",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()
