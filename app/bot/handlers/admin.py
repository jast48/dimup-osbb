import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, desc, delete
from sqlalchemy.orm import selectinload
from app.config import settings
from app.db.session import async_session_maker
from app.db.models import User, Apartment, Ticket, TicketStatus, Bill, Poll, PollOption, PollVote, UserRole
from app.bot.states.user_states import (
    AdminBroadcastState,
    AdminBillState,
    AdminSplitBillState,
    AdminPollState,
    AdminPollEditState
)
from app.bot.keyboards.keyboards import get_main_menu_keyboard, get_admin_panel_keyboard, get_cancel_keyboard
from app.bot.handlers.tickets import CATEGORY_NAMES, URGENCY_NAMES

logger = logging.getLogger(__name__)
router = Router()

# ==========================================
# 1. ЗАЯВКИ (ДИСПЕТЧЕРСКАЯ)
# ==========================================

@router.callback_query(F.data == "admin_tickets_list")
async def cb_admin_tickets(callback: CallbackQuery):
    """Список последних заявок для диспетчера"""
    async with async_session_maker() as session:
        res = await session.execute(
            select(Ticket).order_by(desc(Ticket.created_at)).limit(10)
        )
        tickets = res.scalars().all()
        
    if not tickets:
        await callback.answer("Заявок ще немає.")
        return
        
    await callback.message.delete()
    for t in tickets:
        status_badges = {
            TicketStatus.NEW: "🆕 Нова",
            TicketStatus.IN_PROGRESS: "🛠 В роботі",
            TicketStatus.RESOLVED: "✅ Виконано",
            TicketStatus.CANCELLED: "❌ Відхилено"
        }
        
        async with async_session_maker() as session:
            author_res = await session.execute(select(User).where(User.id == t.creator_id))
            author = author_res.scalar_one_or_none()
            author_name = author.full_name if author else "Невідомо"
            author_phone = author.phone if author else "Немає"
            
            apt_res = await session.execute(select(Apartment).where(Apartment.id == t.apartment_id))
            apt = apt_res.scalar_one_or_none()
            apt_num = apt.number if apt else "—"

        text = (
            f"🎫 <b>Заявка №{t.id}</b> [{status_badges.get(t.status)}]\n"
            f"👤 <b>Мешканець:</b> {author_name} (Кв. №{apt_num})\n"
            f"📞 <b>Тел:</b> {author_phone}\n"
            f"📂 <b>Категорія:</b> {CATEGORY_NAMES.get(t.category)}\n"
            f"⚡️ <b>Срочність:</b> {URGENCY_NAMES.get(t.urgency)}\n\n"
            f"📝 <b>Опис:</b> {t.description}\n"
        )
        if t.ai_summary:
            text += f"💡 <b>AI порада:</b> <i>{t.ai_summary}</i>\n"

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🛠 В роботу", callback_data=f"set_status_{t.id}_in_progress"),
                    InlineKeyboardButton(text="✅ Виконано", callback_data=f"set_status_{t.id}_resolved")
                ],
                [
                    InlineKeyboardButton(text="❌ Відхилити", callback_data=f"set_status_{t.id}_cancelled")
                ]
            ]
        )
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
        
    await callback.message.answer("Керування заявками завершено.", reply_markup=get_admin_panel_keyboard())


@router.callback_query(F.data.startswith("set_status_"))
async def cb_change_status(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split("_")
    ticket_id = int(parts[2])
    status_str = "_".join(parts[3:])
    new_status = TicketStatus(status_str)
    
    async with async_session_maker() as session:
        res = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = res.scalar_one_or_none()
        if ticket:
            ticket.status = new_status
            await session.commit()
            
            author_res = await session.execute(select(User).where(User.id == ticket.creator_id))
            author = author_res.scalar_one_or_none()
            if author:
                if new_status == TicketStatus.RESOLVED:
                    rating_kb = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(text="⭐ 1", callback_data=f"rate_ticket_{ticket.id}_1"),
                                InlineKeyboardButton(text="⭐ 2", callback_data=f"rate_ticket_{ticket.id}_2"),
                                InlineKeyboardButton(text="⭐ 3", callback_data=f"rate_ticket_{ticket.id}_3"),
                                InlineKeyboardButton(text="⭐ 4", callback_data=f"rate_ticket_{ticket.id}_4"),
                                InlineKeyboardButton(text="⭐ 5", callback_data=f"rate_ticket_{ticket.id}_5"),
                            ]
                        ]
                    )
                    try:
                        await bot.send_message(
                            author.telegram_id,
                            f"🎉 <b>Вашу заявку №{ticket.id} успішно виконано!</b>\n\n"
                            f"Будь ласка, оцініть якість роботи майстра від 1 до 5 зірок:",
                            reply_markup=rating_kb,
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
                else:
                    status_titles = {
                        TicketStatus.IN_PROGRESS: "🛠 Вашу заявку взято в роботу майстром.",
                        TicketStatus.CANCELLED: "⚠️ Вашу заявку було відхилено правлінням."
                    }
                    try:
                        await bot.send_message(
                            author.telegram_id,
                            f"🔔 <b>Оновлення по заявці №{ticket.id}:</b>\n{status_titles.get(new_status, '')}",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass

    await callback.answer(f"Статус заявки №{ticket_id} змінено!")
    await callback.message.edit_reply_markup(reply_markup=None)


# ==========================================
# 2. ОПРОСЫ И ГОЛОСОВАНИЯ (ADMIN POLLS)
# ==========================================

@router.callback_query(F.data == "admin_new_poll")
async def cb_admin_polls_menu(callback: CallbackQuery):
    """Меню голосований: создать новое или управлять действующими"""
    await callback.message.delete()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Створити нове опитування", callback_data="admin_poll_create_start")
            ],
            [
                InlineKeyboardButton(text="📊 Керування та результати діючих", callback_data="admin_poll_results")
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back_main")
            ]
        ]
    )
    await callback.message.answer(
        "🗳 <b>Керування опитуваннями та голосуваннями</b>\n\n"
        "Оберіть дію:",
        reply_markup=kb,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin_poll_create_start")
async def cb_start_create_poll(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer(
        "🗳 <b>Створення нового опитування для будинку</b>\n\n"
        "Введіть <b>тему або запитання</b> (наприклад: <i>Встановлення відеоспостереження на поверхах</i>):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(AdminPollState.waiting_for_title)


@router.message(AdminPollState.waiting_for_title, F.text)
async def process_poll_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if len(title) < 5:
        await message.answer("⚠️ Тема опитування має бути довшою (від 5 символів):")
        return
        
    await state.update_data(poll_title=title)
    await message.answer(
        f"Тема: <b>«{title}»</b>\n\n"
        f"Тепер додайте <b>короткий опис / деталі</b> (або напишіть «-» якщо опис не потрібен):",
        parse_mode="HTML"
    )
    await state.set_state(AdminPollState.waiting_for_description)


@router.message(AdminPollState.waiting_for_description, F.text)
async def process_poll_description(message: Message, state: FSMContext):
    desc_text = message.text.strip()
    if desc_text == "-":
        desc_text = None
        
    await state.update_data(poll_description=desc_text)
    
    await message.answer(
        "📝 Введіть <b>варіанти відповідей</b> (розділяйте їх комою або знаком <code>/</code>).\n\n"
        "<i>Приклад:</i>\n"
        "<code>Так, підтримую, Ні, я проти, Потрібно більше інформації</code>",
        parse_mode="HTML"
    )
    await state.set_state(AdminPollState.waiting_for_options)


@router.message(AdminPollState.waiting_for_options, F.text)
async def process_poll_options(message: Message, state: FSMContext, bot: Bot):
    raw_options = message.text.strip()
    
    if "," in raw_options:
        opts_list = [o.strip() for o in raw_options.split(",") if o.strip()]
    elif "/" in raw_options:
        opts_list = [o.strip() for o in raw_options.split("/") if o.strip()]
    elif "\n" in raw_options:
        opts_list = [o.strip() for o in raw_options.split("\n") if o.strip()]
    else:
        opts_list = [raw_options]

    if len(opts_list) < 2:
        await message.answer("⚠️ Введіть щонайменше 2 варіанти відповіді (розділяючи комою):")
        return

    data = await state.get_data()
    title = data.get("poll_title")
    description = data.get("poll_description")

    async with async_session_maker() as session:
        new_poll = Poll(
            title=title,
            description=description,
            is_active=True
        )
        session.add(new_poll)
        await session.flush()

        for opt_text in opts_list:
            session.add(PollOption(poll_id=new_poll.id, text=opt_text))

        await session.commit()
        poll_id = new_poll.id

        users_res = await session.execute(select(User))
        users = users_res.scalars().all()

    desc_str = f"\nℹ️ {description}\n" if description else "\n"
    alert_text = (
        f"🗳 <b>НОВЕ ГОЛОСУВАННЯ В БУДИНКУ!</b>\n\n"
        f"📌 <b>Тема:</b> {title}{desc_str}"
        f"Будь ласка, перейдіть у меню <b>«🗳 Опитування»</b> та віддайте свій голос!"
    )

    sent = 0
    for u in users:
        try:
            await bot.send_message(u.telegram_id, alert_text, parse_mode="HTML")
            sent += 1
        except Exception:
            pass

    await state.clear()
    await message.answer(
        f"🎉 <b>Опитування успішно створено та опубліковано!</b>\n\n"
        f"📌 <b>Тема:</b> {title}\n"
        f"📋 <b>Варіантів:</b> {len(opts_list)}\n"
        f"📨 <b>Сповіщень надіслано:</b> {sent} мешканцям",
        reply_markup=get_main_menu_keyboard(UserRole.ADMIN),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin_poll_results")
async def cb_show_poll_results(callback: CallbackQuery):
    """Просмотр результатов голосований с кнопками редактирования и удаления"""
    async with async_session_maker() as session:
        res = await session.execute(
            select(Poll).options(
                selectinload(Poll.options).selectinload(PollOption.votes)
            ).order_by(desc(Poll.created_at)).limit(10)
        )
        polls = res.scalars().all()

    if not polls:
        await callback.answer("Опитувань ще немає.")
        return

    await callback.message.delete()
    for p in polls:
        total_votes = sum(len(o.votes) for o in p.options)
        status_badge = "🟢 Активне (йде голосування)" if p.is_active else "🔒 Завершено (архів)"
        
        text = (
            f"📊 <b>Опитування №{p.id}: {p.title}</b>\n"
            f"Статус: <b>{status_badge}</b>\n"
        )
        if p.description:
            text += f"<i>{p.description}</i>\n"
        text += f"\n🗳 Всього проголосувало: <b>{total_votes}</b>\n\n"

        for opt in p.options:
            v_count = len(opt.votes)
            pct = (v_count / total_votes * 100) if total_votes > 0 else 0
            text += f"• {opt.text}: <b>{v_count}</b> ({pct:.1f}%)\n"

        toggle_btn_text = "🔒 Завершити" if p.is_active else "🟢 Відкрити знову"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=toggle_btn_text, callback_data=f"poll_toggle_{p.id}"),
                    InlineKeyboardButton(text="✏️ Редагувати", callback_data=f"poll_edit_{p.id}")
                ],
                [
                    InlineKeyboardButton(text="🗑 Видалити опитування", callback_data=f"poll_confirm_del_{p.id}")
                ]
            ]
        )
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")

    await callback.message.answer("Керування опитуваннями:", reply_markup=get_admin_panel_keyboard())


# --- ПЕРЕКЛЮЧЕНИЕ СТАТУСА (ЗАКРЫТЬ / ОТКРЫТЬ) ---

@router.callback_query(F.data.startswith("poll_toggle_"))
async def cb_toggle_poll_status(callback: CallbackQuery):
    poll_id = int(callback.data.split("_")[2])

    async with async_session_maker() as session:
        res = await session.execute(select(Poll).where(Poll.id == poll_id))
        poll = res.scalar_one_or_none()
        if poll:
            poll.is_active = not poll.is_active
            await session.commit()
            new_status = "активовано ✅" if poll.is_active else "завершено/закрито 🔒"
            await callback.answer(f"Опитування №{poll_id} {new_status}!")

    await cb_show_poll_results(callback)


# --- УДАЛЕНИЕ ОПРОСА ---

@router.callback_query(F.data.startswith("poll_confirm_del_"))
async def cb_confirm_delete_poll(callback: CallbackQuery):
    poll_id = int(callback.data.split("_")[3])
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Так, назавжди видалити", callback_data=f"poll_do_delete_{poll_id}"),
                InlineKeyboardButton(text="❌ Скасувати", callback_data="admin_poll_results")
            ]
        ]
    )
    await callback.message.edit_text(
        f"⚠️ <b>Ви впевнені, що хочете видалити опитування №{poll_id}?</b>\n\n"
        f"Усі голоси та варіанти відповідей будуть незворотно видалені з бази даних.",
        reply_markup=kb,
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("poll_do_delete_"))
async def cb_do_delete_poll(callback: CallbackQuery):
    poll_id = int(callback.data.split("_")[3])

    async with async_session_maker() as session:
        res = await session.execute(select(Poll).where(Poll.id == poll_id))
        poll = res.scalar_one_or_none()
        if poll:
            await session.delete(poll)
            await session.commit()

    await callback.answer(f"Опитування №{poll_id} успішно видалено!")
    await callback.message.delete()
    await callback.message.answer(f"✅ Опитування №{poll_id} видалено.", reply_markup=get_admin_panel_keyboard())


# --- РЕДАКТИРОВАНИЕ ОПРОСА ---

@router.callback_query(F.data.startswith("poll_edit_"))
async def cb_start_edit_poll(callback: CallbackQuery, state: FSMContext):
    poll_id = int(callback.data.split("_")[2])
    await state.update_data(edit_poll_id=poll_id)
    
    await callback.message.delete()
    await callback.message.answer(
        f"✏️ <b>Редагування опитування №{poll_id}</b>\n\n"
        f"Введіть <b>нову назву / запитання</b> опитування:",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(AdminPollEditState.waiting_for_title)


@router.message(AdminPollEditState.waiting_for_title, F.text)
async def process_edit_poll_title(message: Message, state: FSMContext):
    title = message.text.strip()
    await state.update_data(new_title=title)
    
    await message.answer(
        f"Нова тема: <b>«{title}»</b>\n\n"
        f"Введіть <b>новий опис</b> (або введіть «-» щоб залишити без опису):",
        parse_mode="HTML"
    )
    await state.set_state(AdminPollEditState.waiting_for_description)


@router.message(AdminPollEditState.waiting_for_description, F.text)
async def process_edit_poll_desc(message: Message, state: FSMContext):
    desc_text = message.text.strip()
    if desc_text == "-":
        desc_text = None

    data = await state.get_data()
    poll_id = data.get("edit_poll_id")
    new_title = data.get("new_title")

    async with async_session_maker() as session:
        res = await session.execute(select(Poll).where(Poll.id == poll_id))
        poll = res.scalar_one_or_none()
        if poll:
            poll.title = new_title
            poll.description = desc_text
            await session.commit()

    await state.clear()
    await message.answer(
        f"✅ <b>Опитування №{poll_id} успішно оновлено!</b>\n\n"
        f"📌 <b>Нова тема:</b> {new_title}\n"
        f"{f'ℹ️ {desc_text}' if desc_text else ''}",
        reply_markup=get_main_menu_keyboard(UserRole.ADMIN),
        parse_mode="HTML"
    )


# ==========================================
# 3. ВЫСТАВЛЕНИЕ СЧЕТОВ
# ==========================================

@router.callback_query(F.data == "admin_create_bill")
async def cb_choose_bill_mode(callback: CallbackQuery):
    await callback.message.delete()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👤 Для однієї квартири", callback_data="bill_mode_single")
            ],
            [
                InlineKeyboardButton(text="🏢 Розподілити на ВСІ квартири будинку", callback_data="bill_mode_split_all")
            ],
            [
                InlineKeyboardButton(text="🔙 Скасувати", callback_data="admin_back_main")
            ]
        ]
    )
    await callback.message.answer(
        "💰 <b>Виставлення рахунків та нарахувань</b>\n\n"
        "Оберіть потрібний варіант нарахування:",
        reply_markup=kb,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "bill_mode_single")
async def cb_start_single_bill(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer(
        "👤 <b>Рахунок для однієї квартири</b>\n\n"
        "Введіть <b>номер квартири</b> (наприклад: <code>5</code>):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(AdminBillState.waiting_for_apt_number)


@router.message(AdminBillState.waiting_for_apt_number, F.text)
async def process_bill_apt(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("⚠️ Будь ласка, введіть тільки число (номер квартири):")
        return
        
    apt_num = int(text)
    async with async_session_maker() as session:
        apt_res = await session.execute(select(Apartment).where(Apartment.number == apt_num))
        apt = apt_res.scalar_one_or_none()
        if not apt:
            await message.answer(f"⚠️ Квартиру №{apt_num} не знайдено в базі. Введіть інший номер:")
            return
            
    await state.update_data(bill_apt_number=apt_num)
    await message.answer(
        f"Квартира №<b>{apt_num}</b> знайдена.\n\n"
        f"Введіть <b>суму нарахування у гривнях</b> (наприклад: <code>850</code> або <code>1250.50</code>):",
        parse_mode="HTML"
    )
    await state.set_state(AdminBillState.waiting_for_amount)


@router.message(AdminBillState.waiting_for_amount, F.text)
async def process_bill_amount(message: Message, state: FSMContext, bot: Bot):
    text = message.text.strip().replace(",", ".")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Будь ласка, введіть коректну суму більше нуля:")
        return

    data = await state.get_data()
    apt_num = data.get("bill_apt_number")
    now = datetime.now()

    async with async_session_maker() as session:
        apt_res = await session.execute(select(Apartment).where(Apartment.number == apt_num))
        apt = apt_res.scalar_one_or_none()

        new_bill = Bill(
            apartment_id=apt.id,
            month=now.month,
            year=now.year,
            amount=amount,
            is_paid=False
        )
        session.add(new_bill)
        apt.balance -= amount
        await session.commit()

        resident_res = await session.execute(select(User).where(User.id == apt.resident_id))
        resident = resident_res.scalar_one_or_none()

    if resident:
        try:
            await bot.send_message(
                resident.telegram_id,
                f"🔔 <b>НОВЕ НАРАХУВАННЯ ЗА КОМУНАЛЬНІ ПОСЛУГИ</b>\n\n"
                f"Шановний(а) <b>{resident.full_name}</b>!\n"
                f"Для квартири №<b>{apt_num}</b> сформовано рахунок: <b>{amount:.2f} грн</b>.\n\n"
                f"<i>Деталі та квитанція доступні у розділі «📱 Кабінет».</i>",
                parse_mode="HTML"
            )
        except Exception:
            pass

    await state.clear()
    await message.answer(
        f"✅ <b>Рахунок успішно виставлено!</b>\n\n"
        f"🏢 <b>Квартира:</b> №{apt_num}\n"
        f"💰 <b>Сума:</b> {amount:.2f} грн\n"
        f"🔔 <b>Сповіщення:</b> {'Надіслано мешканцю в Telegram ✅' if resident else 'Мешканець ще не зареєстрований'}",
        reply_markup=get_main_menu_keyboard(UserRole.ADMIN),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "bill_mode_split_all")
async def cb_start_split_bill(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer(
        "🏢 <b>Масове нарахування на ВСІ квартири</b>\n\n"
        "Введіть <b>призначення платежу</b> (наприклад: <i>Утримання будинку за серпень</i> або <i>Заміна насосу</i>):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(AdminSplitBillState.waiting_for_purpose)


@router.message(AdminSplitBillState.waiting_for_purpose, F.text)
async def process_split_purpose(message: Message, state: FSMContext):
    purpose = message.text.strip()
    await state.update_data(purpose=purpose)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📐 За тарифом на 1 м² (від площі)", callback_data="split_type_area")
            ],
            [
                InlineKeyboardButton(text="⚖️ Порівну на кожну квартиру", callback_data="split_type_equal")
            ],
            [
                InlineKeyboardButton(text="❌ Скасувати", callback_data="admin_back_main")
            ]
        ]
    )
    await message.answer(
        f"Призначення: <b>«{purpose}»</b>\n\n"
        f"Оберіть спосіб розрахунку суми для кожної квартири:",
        reply_markup=kb,
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("split_type_"))
async def process_split_type(callback: CallbackQuery, state: FSMContext):
    split_type = callback.data.replace("split_type_", "")
    await state.update_data(split_type=split_type)
    await callback.message.delete()

    if split_type == "area":
        prompt_text = "Введіть <b>тариф за 1 кв. метр площі</b> (наприклад: <code>8.50</code> або <code>9.20</code> грн/м²):"
    else:
        prompt_text = "Введіть <b>фіксовану суму на кожну квартиру</b> (наприклад: <code>500</code> грн):"

    await callback.message.answer(prompt_text, reply_markup=get_cancel_keyboard(), parse_mode="HTML")
    await state.set_state(AdminSplitBillState.waiting_for_amount)


@router.message(AdminSplitBillState.waiting_for_amount, F.text)
async def process_split_amount(message: Message, state: FSMContext, bot: Bot):
    text = message.text.strip().replace(",", ".")
    try:
        val = float(text)
        if val <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Будь ласка, введіть коректне число більше нуля:")
        return

    data = await state.get_data()
    purpose = data.get("purpose", "Нарахування")
    split_type = data.get("split_type", "equal")
    now = datetime.now()

    loading_msg = await message.answer("⏳ <i>Формуємо рахунки та оновлюємо баланси всіх квартир...</i>", parse_mode="HTML")

    async with async_session_maker() as session:
        res = await session.execute(select(Apartment))
        apartments = res.scalars().all()

        total_billed = 0.0
        bills_to_create = []
        notifications_to_send = []

        for apt in apartments:
            if split_type == "area":
                area = apt.area if apt.area and apt.area > 0 else 60.0
                charge = round(val * area, 2)
            else:
                charge = round(val, 2)

            total_billed += charge
            apt.balance -= charge

            bill = Bill(
                apartment_id=apt.id,
                month=now.month,
                year=now.year,
                amount=charge,
                is_paid=False
            )
            bills_to_create.append(bill)

            if apt.resident_id:
                resident_res = await session.execute(select(User).where(User.id == apt.resident_id))
                resident = resident_res.scalar_one_or_none()
                if resident:
                    notifications_to_send.append((resident.telegram_id, resident.full_name, apt.number, charge))

        session.add_all(bills_to_create)
        await session.commit()

    sent_count = 0
    for tg_id, name, apt_n, ch_amount in notifications_to_send:
        try:
            await bot.send_message(
                tg_id,
                f"🔔 <b>НОВЕ НАРАХУВАННЯ ПО БУДИНКУ</b>\n\n"
                f"Шановний(а) <b>{name}</b>!\n"
                f"Для квартири №<b>{apt_n}</b> сформовано рахунок: <b>{ch_amount:.2f} грн</b>\n"
                f"📌 <b>Призначення:</b> {purpose}\n\n"
                f"<i>Переглянути квитанцію можна у розділі «📱 Кабінет».</i>",
                parse_mode="HTML"
            )
            sent_count += 1
        except Exception:
            pass

    await loading_msg.delete()
    await state.clear()

    summary_text = (
        f"🎉 <b>Масове нарахування успішно виконано!</b>\n\n"
        f"📌 <b>Призначення:</b> {purpose}\n"
        f"🏢 <b>Оброблено квартир:</b> {len(apartments)}\n"
        f"💰 <b>Загальна сума нарахувань:</b> {total_billed:,.2f} грн\n"
        f"📨 <b>Повідомлень надіслано мешканцям:</b> {sent_count}\n"
    )
    await message.answer(summary_text, reply_markup=get_main_menu_keyboard(UserRole.ADMIN), parse_mode="HTML")


@router.message(Command("bill"))
async def cmd_quick_bill(message: Message, bot: Bot):
    telegram_id = message.from_user.id
    
    async with async_session_maker() as session:
        caller_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        caller = caller_res.scalar_one_or_none()
        if not caller or caller.role not in (UserRole.ADMIN, UserRole.BOARD):
            await message.answer("⚠️ Ця команда доступна лише правлінню ОСББ.")
            return

        parts = message.text.split()
        if len(parts) < 3:
            await message.answer("ℹ️ Використання: <code>/bill <номер_квартири> <сума></code>\nНаприклад: <code>/bill 5 850</code>", parse_mode="HTML")
            return

        try:
            apt_num = int(parts[1])
            amount = float(parts[2].replace(",", "."))
        except ValueError:
            await message.answer("⚠️ Некоректні дані. Приклад: <code>/bill 5 850</code>", parse_mode="HTML")
            return

        apt_res = await session.execute(select(Apartment).where(Apartment.number == apt_num))
        apt = apt_res.scalar_one_or_none()
        if not apt:
            await message.answer(f"⚠️ Квартиру №{apt_num} не знайдено.")
            return

        now = datetime.now()
        new_bill = Bill(
            apartment_id=apt.id,
            month=now.month,
            year=now.year,
            amount=amount,
            is_paid=False
        )
        session.add(new_bill)
        apt.balance -= amount
        await session.commit()

        resident_res = await session.execute(select(User).where(User.id == apt.resident_id))
        resident = resident_res.scalar_one_or_none()

    if resident:
        try:
            await bot.send_message(
                resident.telegram_id,
                f"🔔 <b>НОВЕ НАРАХУВАННЯ ЗА КОМУНАЛЬНІ ПОСЛУГИ</b>\n\n"
                f"Шановний(а) <b>{resident.full_name}</b>!\n"
                f"Для квартири №<b>{apt_num}</b> сформовано рахунок: <b>{amount:.2f} грн</b>.\n"
                f"<i>Переглянути квитанцію можна у «📱 Кабінет».</i>",
                parse_mode="HTML"
            )
        except Exception:
            pass

    await message.answer(f"✅ Нараховано <b>{amount:.2f} грн</b> для квартири №<b>{apt_num}</b>!", parse_mode="HTML")


# ==========================================
# 4. РАССЫЛКИ И МЕШКАНЦЫ
# ==========================================

@router.callback_query(F.data == "admin_broadcast")
async def cb_start_broadcast(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer(
        "📢 <b>Створення масової розсилки</b>\n\n"
        "Введіть текст повідомлення, яке буде розіслане <b>всім зареєстрованим мешканцям</b> будинку:",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(AdminBroadcastState.waiting_for_text)


@router.message(AdminBroadcastState.waiting_for_text, F.text)
async def process_broadcast_text(message: Message, state: FSMContext, bot: Bot):
    text = message.text.strip()
    
    async with async_session_maker() as session:
        res = await session.execute(select(User))
        users = res.scalars().all()
        
    count = 0
    for u in users:
        try:
            await bot.send_message(
                u.telegram_id,
                f"📢 <b>ОГОЛОШЕННЯ ВІД ПРАВЛІННЯ ОСББ:</b>\n\n{text}",
                parse_mode="HTML"
            )
            count += 1
        except Exception:
            pass
            
    await state.clear()
    await message.answer(
        f"✅ Розсилку успішно відправлено <b>{count}</b> мешканцям!",
        reply_markup=get_main_menu_keyboard(UserRole.ADMIN),
        parse_mode="HTML"
    )


import html

@router.callback_query(F.data == "admin_residents")
async def cb_residents_list(callback: CallbackQuery, bot: Bot):
    chat_id = callback.from_user.id
    
    try:
        async with async_session_maker() as session:
            res = await session.execute(select(User).order_by(User.id))
            users = res.scalars().all()
            
            apt_res = await session.execute(select(Apartment))
            apts = apt_res.scalars().all()
            user_apt_map = {a.resident_id: a.number for a in apts if a.resident_id}
            
        if not users:
            await callback.answer("Список мешканців порожній.", show_alert=True)
            return

        text = f"👥 <b>Реєстр зареєстрованих користувачів ({len(users)}):</b>\n\n"
        keyboard_buttons = []

        for idx, u in enumerate(users, 1):
            is_owner = (
                u.telegram_id == settings.ADMIN_TELEGRAM_ID 
                or str(getattr(u, "role", "")).lower() == "super_admin" 
                or u.role == UserRole.SUPER_ADMIN
            )
            
            apt_num = user_apt_map.get(u.id, "—")
            
            if is_owner:
                role_badge = "👑 Головний Власник 🔒"
                btn_text = f"🔒 Власник (Кв. №{apt_num})"
                cb_data = "owner_protected_click"
            elif u.role in (UserRole.ADMIN, UserRole.BOARD) or str(getattr(u, "role", "")).lower() in ("admin", "board"):
                role_badge = "👑 Адміністратор"
                btn_text = f"🔻 Зняти адміна (Кв. №{apt_num})"
                cb_data = f"demote_admin_{u.id}"
            else:
                role_badge = "👤 Мешканець"
                btn_text = f"👑 Надати адміна (Кв. №{apt_num})"
                cb_data = f"promote_admin_{u.id}"

            name_clean = html.escape(str(u.full_name or "Без імені"))
            username_clean = f"@{html.escape(str(u.username))}" if u.username else "—"
            phone_clean = html.escape(str(u.phone)) if u.phone else "—"

            text += (
                f"<b>{idx}. {name_clean}</b> ({username_clean})\n"
                f"🏢 Квартира: <b>№{apt_num}</b> | 📱 Тел: {phone_clean}\n"
                f"🏷 Статус: <b>{role_badge}</b>\n\n"
            )
            keyboard_buttons.append([InlineKeyboardButton(text=btn_text, callback_data=cb_data)])

        keyboard_buttons.append([InlineKeyboardButton(text="🔙 Назад до панелі", callback_data="admin_panel_open")])
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        try:
            await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            await bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode="HTML")
            
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in cb_residents_list: {e}")
        await callback.answer("Помилка завантаження реєстру", show_alert=True)


@router.callback_query(F.data == "admin_panel_open")
async def cb_admin_panel_open(callback: CallbackQuery):
    await callback.message.edit_text(
        "🏢 <b>Панель управління ОСББ</b>\n\n"
        "Оберіть потрібну дію з меню нижче:",
        reply_markup=get_admin_panel_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "owner_protected_click")
async def cb_owner_protected(callback: CallbackQuery):
    await callback.answer(
        "🔒 Це Головний Власник системи (Суперадмін).\nЙого права захищені на рівні коду і не можуть бути змінені або зняті!",
        show_alert=True
    )


@router.callback_query(F.data.startswith("promote_admin_"))
async def cb_promote_admin(callback: CallbackQuery, bot: Bot):
    user_id = int(callback.data.split("_")[2])
    
    async with async_session_maker() as session:
        res = await session.execute(select(User).where(User.id == user_id))
        target_user = res.scalar_one_or_none()
        if target_user:
            target_user.role = UserRole.ADMIN
            await session.commit()
            
            try:
                await bot.send_message(
                    target_user.telegram_id,
                    "🎉 <b>Вітаємо!</b> Вам надано права <b>Адміністратора / Правління ОСББ</b>.\n\n"
                    "У вашому меню з'явилася кнопка <b>«🏢 Панель правління»</b>. Натисніть /start для оновлення меню!",
                    reply_markup=get_main_menu_keyboard(UserRole.ADMIN),
                    parse_mode="HTML"
                )
            except Exception:
                pass
                
            await callback.answer(f"Користувача {target_user.full_name} призначено адміністратором!")
            await callback.message.edit_text(
                f"👤 <b>{target_user.full_name}</b>\n🏷 Роль: <b>👑 Голова / Адмін</b> (Права надано ✅)",
                parse_mode="HTML"
            )


@router.callback_query(F.data.startswith("demote_admin_"))
async def cb_demote_admin(callback: CallbackQuery, bot: Bot):
    user_id = int(callback.data.split("_")[2])
    
    async with async_session_maker() as session:
        res = await session.execute(select(User).where(User.id == user_id))
        target_user = res.scalar_one_or_none()
        if target_user:
            # Защита супер-админа
            if target_user.telegram_id == settings.ADMIN_TELEGRAM_ID or target_user.role == UserRole.SUPER_ADMIN:
                await callback.answer("⛔️ Неможливо зняти права з Головного Власника системи!", show_alert=True)
                return

            target_user.role = UserRole.RESIDENT
            await session.commit()
            
            try:
                await bot.send_message(
                    target_user.telegram_id,
                    "ℹ️ Ваші права адміністратора було змінено на стандартний профіль мешканця.",
                    reply_markup=get_main_menu_keyboard(UserRole.RESIDENT),
                    parse_mode="HTML"
                )
            except Exception:
                pass

            await callback.answer(f"Права адміністратора для {target_user.full_name} знято.")
            await callback.message.edit_text(
                f"👤 <b>{target_user.full_name}</b>\n🏷 Роль: <b>👤 Мешканець</b> (Стандартний доступ)",
                parse_mode="HTML"
            )


@router.message(Command("make_admin"))
async def cmd_make_admin(message: Message, bot: Bot):
    telegram_id = message.from_user.id
    
    async with async_session_maker() as session:
        caller_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        caller = caller_res.scalar_one_or_none()
        if not caller or caller.role not in (UserRole.ADMIN, UserRole.BOARD, UserRole.SUPER_ADMIN):
            await message.answer("⚠️ У вас немає прав для виконання цієї команди.")
            return

        parts = message.text.split()
        if len(parts) < 2:
            await message.answer("ℹ️ Використання: <code>/make_admin @username</code> або <code>/make_admin 123456789</code>", parse_mode="HTML")
            return

        target_identifier = parts[1].strip().replace("@", "")

        if target_identifier.isdigit():
            user_query = select(User).where(User.telegram_id == int(target_identifier))
        else:
            user_query = select(User).where(User.username == target_identifier)

        target_res = await session.execute(user_query)
        target_user = target_res.scalar_one_or_none()

        if not target_user:
            await message.answer(f"⚠️ Користувача <b>{target_identifier}</b> не знайдено в базі (він повинен спочатку запустити /start у боті).", parse_mode="HTML")
            return

        target_user.role = UserRole.ADMIN
        await session.commit()

        try:
            await bot.send_message(
                target_user.telegram_id,
                "🎉 <b>Вітаємо!</b> Вам надано права <b>Адміністратора / Правління ОСББ</b>.\n\n"
                "Натисніть /start для переходу до панелі управління!",
                reply_markup=get_main_menu_keyboard(UserRole.ADMIN),
                parse_mode="HTML"
            )
        except Exception:
            pass

        await message.answer(f"✅ Користувачу <b>{target_user.full_name}</b> успішно надано права адміністратора!", parse_mode="HTML")


@router.callback_query(F.data == "admin_back_main")
async def cb_admin_back(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("Ви повернулися в головне меню.", reply_markup=get_main_menu_keyboard(UserRole.ADMIN))
