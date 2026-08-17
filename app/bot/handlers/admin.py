import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, desc, delete, or_
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


async def is_admin_user(telegram_id: int) -> bool:
    """Проверяет, является ли пользователь администратором или владельцем."""
    if telegram_id == settings.ADMIN_TELEGRAM_ID:
        return True
    async with async_session_maker() as session:
        res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = res.scalar_one_or_none()
        return user is not None and user.role in (UserRole.ADMIN, UserRole.BOARD, UserRole.SUPER_ADMIN)


# ==========================================
# 1. ЗАЯВКИ (ДИСПЕТЧЕРСКАЯ)
# ==========================================

@router.callback_query(F.data == "admin_tickets_list")
async def cb_admin_tickets(callback: CallbackQuery):
    """Список активних заявок для диспетчера (Нові та В роботі)"""
    if not await is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ Доступ заборонено.", show_alert=True)
        return
    async with async_session_maker() as session:
        res = await session.execute(
            select(Ticket).where(
                Ticket.status.in_([TicketStatus.NEW, TicketStatus.IN_PROGRESS])
            ).order_by(desc(Ticket.created_at)).limit(15)
        )
        tickets = res.scalars().all()
        
    if not tickets:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📦 Переглянути архів завершених заявок", callback_data="admin_tickets_archive")],
                [InlineKeyboardButton(text="🔙 Панель правління", callback_data="admin_back_main")]
            ]
        )
        await callback.message.edit_text(
            "🎉 <b>Усі заявки опрацьовано!</b>\n\n"
            "Наразі немає активних або невиконаних заявок.\n"
            "Всі попередні заявки успішно переміщено в архів.",
            reply_markup=kb,
            parse_mode="HTML"
        )
        return
        
    await callback.message.delete()
    for t in tickets:
        status_badges = {
            TicketStatus.NEW: "🆕 Нова",
            TicketStatus.IN_PROGRESS: "🛠 В роботі"
        }
        
        async with async_session_maker() as session:
            author_res = await session.execute(select(User).where(User.id == t.creator_id))
            author = author_res.scalar_one_or_none()
            author_name = author.full_name if author else "Невідомо"
            author_phone = author.phone if author else "Немає"
            
            apt_res = await session.execute(select(Apartment).where(Apartment.id == t.apartment_id))
            apt = apt_res.scalar_one_or_none()
            apt_num = apt.number if apt else "—"

            assigned_master_name = None
            if t.assigned_to_id:
                m_res = await session.execute(select(User).where(User.id == t.assigned_to_id))
                m_obj = m_res.scalar_one_or_none()
                if m_obj:
                    assigned_master_name = m_obj.full_name

        voice_status = "✅ Є аудіозапис" if t.audio_file_id else "📝 Текстова"
        photo_status = "✅ Є фото" if t.photo_file_id else "❌ Немає"

        master_line = f"\n👷‍♂️ <b>Призначений майстер:</b> {assigned_master_name}" if assigned_master_name else ""

        text = (
            f"🎫 <b>Заявка №{t.id}</b> [{status_badges.get(t.status, '🛠 В роботі')}]\n"
            f"👤 <b>Мешканець:</b> {author_name} (Кв. №{apt_num})\n"
            f"📞 <b>Тел:</b> {author_phone}\n"
            f"📂 <b>Категорія:</b> {CATEGORY_NAMES.get(t.category)}\n"
            f"⚡️ <b>Срочність:</b> {URGENCY_NAMES.get(t.urgency)}{master_line}\n"
            f"🎙 <b>Аудіо:</b> {voice_status} | 📷 <b>Фото:</b> {photo_status}\n\n"
            f"📝 <b>Опис:</b> {t.description}\n"
        )
        if t.ai_summary:
            text += f"💡 <b>AI порада:</b> <i>{t.ai_summary}</i>\n"

        buttons = [
            [
                InlineKeyboardButton(text="📄 Текст заявки", callback_data=f"show_ticket_text_{t.id}"),
                InlineKeyboardButton(text="🎙 Голосове", callback_data=f"show_ticket_voice_{t.id}"),
                InlineKeyboardButton(text="📷 Фото", callback_data=f"show_ticket_photo_{t.id}")
            ],
            [
                InlineKeyboardButton(text="👷‍♂️ Призначити майстра", callback_data=f"assign_master_ticket_{t.id}"),
                InlineKeyboardButton(text="🛠 В роботу", callback_data=f"set_status_{t.id}_in_progress")
            ],
            [
                InlineKeyboardButton(text="✅ Виконано", callback_data=f"set_status_{t.id}_resolved"),
                InlineKeyboardButton(text="❌ Відхилити", callback_data=f"set_status_{t.id}_cancelled")
            ]
        ]

        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
        
    footer_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📦 Переглянути архів завершених заявок", callback_data="admin_tickets_archive")],
            [InlineKeyboardButton(text="🔙 Панель правління", callback_data="admin_back_main")]
        ]
    )
    await callback.message.answer("Активні заявки будинку:", reply_markup=footer_kb)


@router.callback_query(F.data.startswith("show_ticket_text_"))
async def cb_show_ticket_text(callback: CallbackQuery):
    ticket_id = int(callback.data.split("_")[3])
    async with async_session_maker() as session:
        res = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = res.scalar_one_or_none()
        if not ticket:
            await callback.answer("Заявку не знайдено.", show_alert=True)
            return
            
        author_res = await session.execute(select(User).where(User.id == ticket.creator_id))
        author = author_res.scalar_one_or_none()
        author_name = author.full_name if author else "Мешканець"
        
        apt_res = await session.execute(select(Apartment).where(Apartment.id == ticket.apartment_id))
        apt = apt_res.scalar_one_or_none()
        apt_num = apt.number if apt else "—"

    voice_badge = "🎙 <b>Голосове повідомлення:</b> Прикріплено до заявки ✅\n" if ticket.audio_file_id else "📝 <b>Формат:</b> Текстове звернення\n"
    photo_badge = "📷 <b>Фото поломки:</b> Прикріплено до заявки ✅\n" if ticket.photo_file_id else "📷 <b>Фото:</b> Не додавалося\n"

    details_text = (
        f"📄 <b>ПОВНИЙ ТЕКСТ ТА ДЕТАЛІ ЗАЯВКИ №{ticket.id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Автор:</b> {author_name} (Кв. №{apt_num})\n"
        f"📅 <b>Створено:</b> {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        f"📂 <b>Категорія:</b> {CATEGORY_NAMES.get(ticket.category)}\n"
        f"⚡️ <b>Срочність:</b> {URGENCY_NAMES.get(ticket.urgency)}\n"
        f"{voice_badge}{photo_badge}\n"
        f"📝 <b>Текст звернення:</b>\n<i>«{ticket.description}»</i>\n\n"
        f"🤖 <b>AI-висновок та порада:</b>\n{ticket.ai_summary or '—'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    await callback.message.answer(details_text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("show_ticket_voice_"))
async def cb_show_ticket_voice(callback: CallbackQuery, bot: Bot):
    ticket_id = int(callback.data.split("_")[3])
    async with async_session_maker() as session:
        res = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = res.scalar_one_or_none()
        if not ticket:
            await callback.answer("Заявку не знайдено.", show_alert=True)
            return
        if not ticket.audio_file_id:
            await callback.answer("🎙 Це була текстова заявка, голосовий запис не додавався.", show_alert=True)
            return

        author_res = await session.execute(select(User).where(User.id == ticket.creator_id))
        author = author_res.scalar_one_or_none()
        author_name = author.full_name if author else "Мешканця"

    try:
        await bot.send_voice(
            chat_id=callback.from_user.id,
            voice=ticket.audio_file_id,
            caption=f"🎙 <b>Оригінальний голосовий запис до заявки №{ticket.id}</b>\nВід: {author_name}",
            parse_mode="HTML"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error sending voice: {e}")
        await callback.answer("Не вдалося відправити аудіофайл.", show_alert=True)


@router.callback_query(F.data.startswith("show_ticket_photo_"))
async def cb_show_ticket_photo(callback: CallbackQuery, bot: Bot):
    ticket_id = int(callback.data.split("_")[3])
    async with async_session_maker() as session:
        res = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = res.scalar_one_or_none()
        if not ticket:
            await callback.answer("Заявку не знайдено.", show_alert=True)
            return
        if not ticket.photo_file_id:
            await callback.answer("📷 Мешканець не прикріплював фото до цієї заявки.", show_alert=True)
            return

    try:
        await bot.send_photo(
            chat_id=callback.from_user.id,
            photo=ticket.photo_file_id,
            caption=f"📷 <b>Фото поломки до заявки №{ticket.id}</b>",
            parse_mode="HTML"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error sending photo: {e}")
        await callback.answer("Не вдалося відправити фото.", show_alert=True)


@router.callback_query(F.data.startswith("set_status_"))
async def cb_change_status(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ Доступ заборонено.", show_alert=True)
        return

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
    
    if new_status == TicketStatus.RESOLVED:
        await callback.message.edit_text(
            f"✅ <b>Заявку №{ticket_id} успішно виконано та переміщено в архів! 📦</b>\n\n"
            f"<i>Мешканцю надіслано запит на оцінку якості робіт (1-5 ⭐).</i>",
            parse_mode="HTML"
        )
    elif new_status == TicketStatus.CANCELLED:
        await callback.message.edit_text(
            f"❌ <b>Заявку №{ticket_id} відхилено та переміщено в архів! 📦</b>",
            parse_mode="HTML"
        )
    elif new_status == TicketStatus.IN_PROGRESS:
        # Обновляем клавиатуру — оставляем только кнопки завершения/отклонения
        in_progress_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📄 Текст заявки", callback_data=f"show_ticket_text_{ticket_id}"),
                    InlineKeyboardButton(text="🎙 Голосове", callback_data=f"show_ticket_voice_{ticket_id}"),
                    InlineKeyboardButton(text="📷 Фото", callback_data=f"show_ticket_photo_{ticket_id}")
                ],
                [
                    InlineKeyboardButton(text="✅ Позначити як Виконано", callback_data=f"set_status_{ticket_id}_resolved"),
                    InlineKeyboardButton(text="❌ Відхилити", callback_data=f"set_status_{ticket_id}_cancelled")
                ]
            ]
        )
        try:
            await callback.message.edit_reply_markup(reply_markup=in_progress_kb)
        except Exception:
            pass


@router.callback_query(F.data.startswith("assign_master_ticket_"))
async def cb_assign_master_ticket(callback: CallbackQuery):
    """Вибір майстра для призначення на заявку"""
    if not await is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ Доступ заборонено.", show_alert=True)
        return

    ticket_id = int(callback.data.split("_")[3])
    async with async_session_maker() as session:
        masters_res = await session.execute(
            select(User).where(
                or_(User.role == UserRole.CONTRACTOR, User.contractor_category.isnot(None))
            ).order_by(desc(User.contractor_rating))
        )
        masters = masters_res.scalars().all()

    if not masters:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➕ Зареєструвати майстра", callback_data="start_register_contractor")],
                [InlineKeyboardButton(text="🔙 До заявок", callback_data="admin_tickets_list")]
            ]
        )
        await callback.message.edit_text(
            f"⚠️ <b>Немає зареєстрованих майстрів у базі!</b>\n\n"
            f"Зареєструйте майстрів через кнопку або запропонуйте їм перейти в бота та обрати роль «🛠 Підрядник».",
            reply_markup=kb,
            parse_mode="HTML"
        )
        return

    buttons = []
    for m in masters:
        cat_badge = m.contractor_category or "Майстер"
        rating_badge = f"⭐ {m.contractor_rating:.1f}" if m.contractor_rating else "⭐ 5.0"
        buttons.append([
            InlineKeyboardButton(
                text=f"👷‍♂️ {m.full_name} ({cat_badge}, {rating_badge})",
                callback_data=f"exec_assign_{ticket_id}_{m.id}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Скасувати", callback_data="admin_tickets_list")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        f"👷‍♂️ <b>ПРИЗНАЧЕННЯ МАЙСТРА НА ЗАЯВКУ №{ticket_id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Оберіть спеціаліста зі списку нижче:\n"
        f"<i>(Після вибору майстер миттєво отримає сповіщення з описом проблеми та контактами мешканця)</i>",
        reply_markup=kb,
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("exec_assign_"))
async def cb_exec_assign_master(callback: CallbackQuery, bot: Bot):
    """Фіксація призначення майстра на заявку та сповіщення сторін"""
    if not await is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ Доступ заборонено.", show_alert=True)
        return

    parts = callback.data.split("_")
    ticket_id = int(parts[2])
    master_id = int(parts[3])

    async with async_session_maker() as session:
        ticket_res = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = ticket_res.scalar_one_or_none()

        master_res = await session.execute(select(User).where(User.id == master_id))
        master = master_res.scalar_one_or_none()

        if not ticket or not master:
            await callback.answer("Заявку або майстра не знайдено.")
            return

        ticket.assigned_to_id = master.id
        ticket.status = TicketStatus.IN_PROGRESS
        await session.commit()

        # Отримуємо автора заявки
        author_res = await session.execute(select(User).where(User.id == ticket.creator_id))
        author = author_res.scalar_one_or_none()

        apt_res = await session.execute(select(Apartment).where(Apartment.id == ticket.apartment_id))
        apt = apt_res.scalar_one_or_none()
        apt_num = apt.number if apt else "—"

    await callback.answer(f"✅ Майстра {master.full_name} призначено!", show_alert=True)
    await callback.message.edit_text(
        f"✅ <b>Майстра {master.full_name} успішно призначено на заявку №{ticket_id}!</b>\n\n"
        f"📌 Статус заявки змінено на <b>«🛠 В роботі»</b>.\n"
        f"🔔 Майстер та мешканець отримали сповіщення у боті.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 До списку заявок", callback_data="admin_tickets_list")]]
        ),
        parse_mode="HTML"
    )

    # 1. Сповіщення призначеному майстру
    if master.telegram_id:
        try:
            master_kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="🏁 Роботу виконано", callback_data=f"set_status_{ticket_id}_resolved")
                    ]
                ]
            )
            await bot.send_message(
                chat_id=master.telegram_id,
                text=(
                    f"🚨 <b>ВАС ПРИЗНАЧЕНО НА ЗАЯВКУ №{ticket_id}!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 <b>Замовник:</b> {author.full_name if author else 'Мешканець'} (Квартира №{apt_num})\n"
                    f"📱 <b>Телефон:</b> <code>{author.phone if author and author.phone else '—'}</code>\n"
                    f"📂 <b>Категорія:</b> {CATEGORY_NAMES.get(ticket.category, 'Загальна')}\n"
                    f"⚡️ <b>Срочність:</b> {URGENCY_NAMES.get(ticket.urgency, 'Звичайна')}\n\n"
                    f"📝 <b>Опис проблеми:</b>\n{ticket.description}\n\n"
                    f"💡 <b>AI порада:</b> <i>{ticket.ai_summary or '—'}</i>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"<i>Будь ласка, зв'яжіться з мешканцем або прибудьте для усунення несправності. Після завершення натисніть «🏁 Роботу виконано».</i>"
                ),
                reply_markup=master_kb,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.debug("Failed to notify assigned master: %s", e)

    # 2. Сповіщення мешканцю
    if author and author.telegram_id:
        try:
            await bot.send_message(
                chat_id=author.telegram_id,
                text=(
                    f"ℹ️ <b>Оновлення по вашій заявці №{ticket_id}:</b>\n\n"
                    f"Правління призначило відповідального спеціаліста:\n"
                    f"👷‍♂️ <b>Майстер:</b> {master.full_name}\n"
                    f"📌 <b>Спеціалізація:</b> {master.contractor_category or 'Служба ОСББ'}\n"
                    f"📱 <b>Телефон для зв'язку:</b> <code>{master.phone or 'Вказано в базі'}</code>\n\n"
                    f"<i>Спеціаліст зв'яжеться з вами найближчим часом.</i>"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.debug("Failed to notify resident: %s", e)


@router.callback_query(F.data == "admin_contractors_list")
async def cb_admin_contractors_list(callback: CallbackQuery):
    """Реєстр майстрів та підрядників будинку в панелі правління"""
    if not await is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ Доступ заборонено.", show_alert=True)
        return

    async with async_session_maker() as session:
        masters_res = await session.execute(
            select(User).where(
                or_(User.role == UserRole.CONTRACTOR, User.contractor_category.isnot(None))
            ).order_by(desc(User.contractor_rating))
        )
        masters = masters_res.scalars().all()

    buttons = [
        [InlineKeyboardButton(text="➕ Зареєструвати нового майстра", callback_data="start_register_contractor")],
        [InlineKeyboardButton(text="🔙 Панель правління", callback_data="admin_back_main")]
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if not masters:
        text = (
            "👷‍♂️ <b>РЕЄСТР МАЙСТРІВ ТА ПІДРЯДНИКІВ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Наразі в системі немає зареєстрованих підрядників.\n\n"
            "Ви можете додати майстра самостійно через кнопку <b>«➕ Зареєструвати нового майстра»</b> або надіслати йому посилання на бота."
        )
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        return

    text = f"👷‍♂️ <b>РЕЄСТР МАЙСТРІВ ТА ПІДРЯДНИКІВ БУДИНКУ ({len(masters)})</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for idx, m in enumerate(masters, 1):
        cat = m.contractor_category or "Універсальний спеціаліст"
        company = f" ({m.contractor_company})" if m.contractor_company else ""
        rating = m.contractor_rating or 5.0
        orders = m.contractor_orders_count or 0
        phone = m.phone or "Не вказано"
        tg = f"@{m.username}" if m.username else "—"

        text += (
            f"<b>{idx}. {m.full_name}</b>{company}\n"
            f"   📌 <b>Спеціалізація:</b> {cat}\n"
            f"   ⭐️ <b>Рейтинг:</b> {rating:.2f} / 5.0 (Виконано робіт: {orders})\n"
            f"   📱 <b>Телефон:</b> <code>{phone}</code> | <b>TG:</b> {tg}\n\n"
        )

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "admin_tickets_archive")
async def cb_admin_tickets_archive(callback: CallbackQuery):
    """Архив выполненных и отклоненных заявок"""
    if not await is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ Доступ заборонено.", show_alert=True)
        return

    async with async_session_maker() as session:
        res = await session.execute(
            select(Ticket).where(
                Ticket.status.in_([TicketStatus.RESOLVED, TicketStatus.CANCELLED])
            ).order_by(desc(Ticket.updated_at)).limit(15)
        )
        archived_tickets = res.scalars().all()

    if not archived_tickets:
        await callback.answer("Архів завершених заявок порожній.", show_alert=True)
        return

    await callback.message.delete()
    for t in archived_tickets:
        status_label = "✅ Виконано" if t.status == TicketStatus.RESOLVED else "❌ Відхилено"
        rating_str = f" | Оцінка: {'⭐' * t.rating}" if t.rating else ""

        async with async_session_maker() as session:
            author_res = await session.execute(select(User).where(User.id == t.creator_id))
            author = author_res.scalar_one_or_none()
            author_name = author.full_name if author else "Мешканець"
            
            apt_res = await session.execute(select(Apartment).where(Apartment.id == t.apartment_id))
            apt = apt_res.scalar_one_or_none()
            apt_num = apt.number if apt else "—"

        voice_status = "✅ Є аудіо" if t.audio_file_id else "📝 Текст"
        photo_status = "✅ Є фото" if t.photo_file_id else "❌ Немає"

        text = (
            f"📦 <b>Архівна заявка №{t.id}</b> [{status_label}{rating_str}]\n"
            f"👤 <b>Мешканець:</b> {author_name} (Кв. №{apt_num})\n"
            f"📅 <b>Створено:</b> {t.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"🎙 <b>Аудіо:</b> {voice_status} | 📷 <b>Фото:</b> {photo_status}\n\n"
            f"📝 <b>Опис:</b> {t.description}\n"
        )

        buttons = [
            [
                InlineKeyboardButton(text="📄 Текст заявки", callback_data=f"show_ticket_text_{t.id}"),
                InlineKeyboardButton(text="🎙 Голосове", callback_data=f"show_ticket_voice_{t.id}"),
                InlineKeyboardButton(text="📷 Фото", callback_data=f"show_ticket_photo_{t.id}")
            ]
        ]
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")

    back_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛠 До активних заявок", callback_data="admin_tickets_list")],
            [InlineKeyboardButton(text="🔙 Панель правління", callback_data="admin_back_main")]
        ]
    )
    await callback.message.answer("Кінець архіву заявок:", reply_markup=back_kb)


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
    if not await is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ Доступ заборонено.", show_alert=True)
        return
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
    if not await is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ Доступ заборонено.", show_alert=True)
        return
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
        f"📝 Тепер введіть <b>призначення платежу (за що рахунок)</b>:\n"
        f"<i>(Наприклад: «Утримання будинку за серпень», «Ремонт покрівлі», «Цільовий внесок на генератор» або «Опалення»)</i>",
        parse_mode="HTML"
    )
    await state.set_state(AdminBillState.waiting_for_description)


@router.message(AdminBillState.waiting_for_description, F.text)
async def process_bill_description(message: Message, state: FSMContext):
    description = message.text.strip()
    if len(description) < 2:
        await message.answer("⚠️ Будь ласка, введіть зрозумілий опис (призначення платежу):")
        return

    await state.update_data(bill_description=description)
    await message.answer(
        f"Призначення: <b>«{description}»</b>\n\n"
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
    description = data.get("bill_description") or "Утримання будинку та прибудинкової території"
    now = datetime.now()

    async with async_session_maker() as session:
        apt_res = await session.execute(select(Apartment).where(Apartment.number == apt_num))
        apt = apt_res.scalar_one_or_none()

        new_bill = Bill(
            apartment_id=apt.id,
            month=now.month,
            year=now.year,
            amount=amount,
            description=description,
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
                f"📌 <b>Призначення:</b> {description}\n\n"
                f"<i>Деталі та квитанція доступні у розділі «📱 Кабінет».</i>",
                parse_mode="HTML"
            )
        except Exception:
            pass

    await state.clear()
    await message.answer(
        f"✅ <b>Рахунок успішно виставлено!</b>\n\n"
        f"🏢 <b>Квартира:</b> №{apt_num}\n"
        f"📌 <b>Призначення:</b> {description}\n"
        f"💰 <b>Сума:</b> {amount:.2f} грн\n"
        f"🔔 <b>Сповіщення:</b> {'Надіслано мешканцю в Telegram ✅' if resident else 'Мешканець ще не зареєстрований'}",
        reply_markup=get_main_menu_keyboard(UserRole.ADMIN),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "bill_mode_split_all")
async def cb_start_split_bill(callback: CallbackQuery, state: FSMContext):
    if not await is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ Доступ заборонено.", show_alert=True)
        return
    await callback.message.delete()
    await callback.message.answer(
        "🏢 <b>Масове нарахування на ВСІ квартири</b>\n\n"
        "Введіть <b>призначення платежу (за що рахунок)</b>:\n"
        "<i>(Наприклад: «Утримання будинку за серпень», «Заміна насосу», «Цільовий внесок на відеонагляд»)</i>",
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
    if not await is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ Доступ заборонено.", show_alert=True)
        return
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
    purpose = data.get("purpose", "Утримання будинку та прибудинкової території")
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
                description=purpose,
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
    if not await is_admin_user(telegram_id):
        await message.answer("⚠️ Ця команда доступна лише правлінню ОСББ.")
        return
    
    async with async_session_maker() as session:
        parts = message.text.split(maxsplit=3)
        if len(parts) < 3:
            await message.answer("ℹ️ Використання: <code>/bill <номер_квартири> <сума> [опис]</code>\nНаприклад: <code>/bill 5 850 Ремонт ліфта</code>", parse_mode="HTML")
            return

        try:
            apt_num = int(parts[1])
            amount = float(parts[2].replace(",", "."))
        except ValueError:
            await message.answer("⚠️ Некоректні дані. Приклад: <code>/bill 5 850 Ремонт ліфта</code>", parse_mode="HTML")
            return

        description = parts[3].strip() if len(parts) >= 4 else "Утримання будинку та прибудинкової території"

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
            description=description,
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
                f"📌 <b>Призначення:</b> {description}\n\n"
                f"<i>Переглянути квитанцію можна у «📱 Кабінет».</i>",
                parse_mode="HTML"
            )
        except Exception:
            pass

    await message.answer(f"✅ Нараховано <b>{amount:.2f} грн</b> («{description}») для квартири №<b>{apt_num}</b>!", parse_mode="HTML")


# ==========================================
# 4. РАССЫЛКИ И МЕШКАНЦЫ
# ==========================================

@router.callback_query(F.data == "admin_broadcast")
async def cb_start_broadcast(callback: CallbackQuery, state: FSMContext):
    if not await is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ Доступ заборонено.", show_alert=True)
        return
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
                f"📢 <b>ОГОЛОШЕННЯ ВІД ПРАВЛІННЯ ОСББ:</b>\n\n{html.escape(text)}",
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
    if not await is_admin_user(chat_id):
        await callback.answer("⛔️ Доступ заборонено.", show_alert=True)
        return
    
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

        try:
            await callback.message.delete()
        except Exception:
            pass

        await bot.send_message(
            chat_id,
            f"👥 <b>Реєстр зареєстрованих мешканців ({len(users)}):</b>\n"
            "<i>Керуйте правами доступу окремо по кожному мешканцю:</i>",
            parse_mode="HTML"
        )

        for u in users:
            is_owner = (
                u.telegram_id == settings.ADMIN_TELEGRAM_ID 
                or str(getattr(u, "role", "")).lower() == "super_admin" 
                or u.role == UserRole.SUPER_ADMIN
            )
            
            apt_num = user_apt_map.get(u.id, "—")
            
            if is_owner:
                role_badge = "👑 Головний Власник 🔒"
                btn_text = "🔒 Права захищено (Власник)"
                cb_data = "owner_protected_click"
            elif u.role in (UserRole.ADMIN, UserRole.BOARD) or str(getattr(u, "role", "")).lower() in ("admin", "board"):
                role_badge = "👑 Голова / Адмін"
                btn_text = "🔻 Зняти права адміна"
                cb_data = f"demote_admin_{u.id}"
            else:
                role_badge = "👤 Мешканець"
                btn_text = "👑 Надати права адміна"
                cb_data = f"promote_admin_{u.id}"

            name_clean = html.escape(str(u.full_name or "Без імені"))
            username_clean = f"@{html.escape(str(u.username))}" if u.username else "без_юзернейма"
            phone_clean = html.escape(str(u.phone)) if u.phone else "—"

            card_text = (
                f"👤 <b>{name_clean}</b> ({username_clean})\n"
                f"🏢 Квартира: <b>№{apt_num}</b>\n"
                f"📱 Тел: <code>{phone_clean}</code>\n"
                f"🏷 Статус: <b>{role_badge}</b>"
            )

            kb = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=btn_text, callback_data=cb_data)]]
            )
            await bot.send_message(chat_id, card_text, reply_markup=kb, parse_mode="HTML")

        await bot.send_message(chat_id, "Панель управління:", reply_markup=get_admin_panel_keyboard())
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in cb_residents_list: {e}")
        await callback.answer("Помилка завантаження реєстру", show_alert=True)


@router.callback_query(F.data == "owner_protected_click")
async def cb_owner_protected(callback: CallbackQuery):
    await callback.answer(
        "🔒 Це Головний Власник системи (Суперадмін).\nЙого права захищені на рівні коду і не можуть бути змінені або зняті!",
        show_alert=True
    )


@router.callback_query(F.data.startswith("promote_admin_"))
async def cb_promote_admin(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ Доступ заборонено.", show_alert=True)
        return
    user_id = int(callback.data.split("_")[2])
    
    async with async_session_maker() as session:
        res = await session.execute(select(User).where(User.id == user_id))
        target_user = res.scalar_one_or_none()
        if target_user:
            target_user.role = UserRole.ADMIN
            await session.commit()
            
            apt_res = await session.execute(select(Apartment).where(Apartment.resident_id == target_user.id))
            apt = apt_res.scalar_one_or_none()
            apt_num = apt.number if apt else "—"
            
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
            
            name_clean = html.escape(str(target_user.full_name or "Без імені"))
            username_clean = f"@{html.escape(str(target_user.username))}" if target_user.username else "без_юзернейма"
            phone_clean = html.escape(str(target_user.phone)) if target_user.phone else "—"
            
            new_text = (
                f"👤 <b>{name_clean}</b> ({username_clean})\n"
                f"🏢 Квартира: <b>№{apt_num}</b>\n"
                f"📱 Тел: <code>{phone_clean}</code>\n"
                f"🏷 Статус: <b>👑 Голова / Адмін (Права надано ✅)</b>"
            )
            new_kb = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔻 Зняти права адміна", callback_data=f"demote_admin_{target_user.id}")]]
            )
            await callback.message.edit_text(new_text, reply_markup=new_kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("demote_admin_"))
async def cb_demote_admin(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(callback.from_user.id):
        await callback.answer("⛔️ Доступ заборонено.", show_alert=True)
        return
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
            
            apt_res = await session.execute(select(Apartment).where(Apartment.resident_id == target_user.id))
            apt = apt_res.scalar_one_or_none()
            apt_num = apt.number if apt else "—"
            
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
            
            name_clean = html.escape(str(target_user.full_name or "Без імені"))
            username_clean = f"@{html.escape(str(target_user.username))}" if target_user.username else "без_юзернейма"
            phone_clean = html.escape(str(target_user.phone)) if target_user.phone else "—"
            
            new_text = (
                f"👤 <b>{name_clean}</b> ({username_clean})\n"
                f"🏢 Квартира: <b>№{apt_num}</b>\n"
                f"📱 Тел: <code>{phone_clean}</code>\n"
                f"🏷 Статус: <b>👤 Мешканець (Звичайний доступ)</b>"
            )
            new_kb = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="👑 Надати права адміна", callback_data=f"promote_admin_{target_user.id}")]]
            )
            await callback.message.edit_text(new_text, reply_markup=new_kb, parse_mode="HTML")


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
