from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, desc
from app.db.session import async_session_maker
from app.db.models import (
    User,
    Apartment,
    Announcement,
    Poll,
    PollOption,
    PollVote,
    Bill,
    Ticket,
    MeterReading,
    UserRole
)
from app.bot.states.user_states import MeterReadingState
from app.bot.keyboards.keyboards import get_main_menu_keyboard, get_admin_panel_keyboard, get_cancel_keyboard
from app.config import settings

router = Router()

# ==========================================
# 1. ОСОБИСТИЙ КАБІНЕТ & ВЕБ-ДОДАТОК
# ==========================================

@router.message(F.text.contains("Кабінет"))
async def cmd_webapp_info(message: Message, state: FSMContext):
    """Информация о личном кабинете, балансе и квитанциях"""
    await state.clear()
    telegram_id = message.from_user.id
    
    async with async_session_maker() as session:
        res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = res.scalar_one_or_none()
        
        if not user:
            await message.answer("⚠️ Будь ласка, спочатку пройдіть реєстрацію через /start.")
            return

        apt_res = await session.execute(select(Apartment).where(Apartment.resident_id == user.id))
        apt = apt_res.scalar_one_or_none()
        
        apt_num = apt.number if apt else 1
        balance = apt.balance if apt else 0.0
        area = apt.area if apt and apt.area else 60.0

        bills = []
        if apt:
            bills_res = await session.execute(
                select(Bill).where(Bill.apartment_id == apt.id).order_by(desc(Bill.id)).limit(3)
            )
            bills = bills_res.scalars().all()

    status_str = "🟢 Оплачено (без боргів)" if balance >= 0 else f"🔴 Заборгованість: {abs(balance):.2f} грн"

    text = (
        f"📱 <b>Особистий кабінет мешканця</b>\n\n"
        f"👤 <b>Власник:</b> {user.full_name}\n"
        f"🏢 <b>Квартира:</b> №{apt_num} (Площа: {area} м²)\n"
        f"💳 <b>Поточний баланс:</b> {status_str}\n\n"
        f"📄 <b>Останні нарахування:</b>\n"
    )

    if bills:
        for b in bills:
            pay_badge = "Сплачено ✅" if b.is_paid else "Очікує оплати ⏳"
            text += f"• Місяць {b.month}/{b.year}: <b>{b.amount:.2f} грн</b> ({pay_badge})\n"
    else:
        text += "• <i>Нарахувань за поточний період немає.</i>\n"

    kb_buttons = []
    if settings.WEBAPP_URL and settings.WEBAPP_URL.startswith("https://"):
        webapp_full_url = f"{settings.WEBAPP_URL}?apt_num={apt_num}"
        kb_buttons.append([InlineKeyboardButton(text="🚀 Відкрити WebApp Mini App", web_app=WebAppInfo(url=webapp_full_url))])
    
    kb_buttons.append([
        InlineKeyboardButton(text="💳 Сплатити рахунок онлайн", callback_data="pay_bills_start"),
        InlineKeyboardButton(text="📊 Показники лічильників", callback_data="meters_start")
    ])
    kb_buttons.append([
        InlineKeyboardButton(text="🛠 Замовити платну послугу", callback_data="mkt_back_main")
    ])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


# ==========================================
# 2. ПЕРЕДАЧА ПОКАЗАНИЙ СЧЕТЧИКОВ (ЛІЧИЛЬНИКИ)
# ==========================================

@router.callback_query(F.data == "meters_start")
@router.message(F.text.contains("Лічильник") | F.text.contains("Показник"))
async def start_meter_readings(event: Message | CallbackQuery, state: FSMContext):
    await state.clear()
    message = event if isinstance(event, Message) else event.message
    
    text = (
        "📊 <b>Передача показників лічильників</b>\n\n"
        "Введіть поточні показники <b>холодної води (м³)</b>:\n"
        "<i>(Наприклад: <code>142.5</code> або <code>142</code>)</i>"
    )
    await message.answer(text, reply_markup=get_cancel_keyboard(), parse_mode="HTML")
    await state.set_state(MeterReadingState.waiting_for_cold_water)


@router.message(MeterReadingState.waiting_for_cold_water, F.text)
async def process_cold_water(message: Message, state: FSMContext):
    val_str = message.text.strip().replace(",", ".")
    try:
        cold = float(val_str)
        if cold < 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введіть коректне число для холодної води:")
        return

    await state.update_data(cold_water=cold)
    await message.answer(
        "♨️ Введіть поточні показники <b>гарячої води (м³)</b>:\n"
        "<i>(Якщо у вас бойлер або немає гарячої води — введіть <code>0</code>)</i>",
        parse_mode="HTML"
    )
    await state.set_state(MeterReadingState.waiting_for_hot_water)


@router.message(MeterReadingState.waiting_for_hot_water, F.text)
async def process_hot_water(message: Message, state: FSMContext):
    val_str = message.text.strip().replace(",", ".")
    try:
        hot = float(val_str)
        if hot < 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введіть коректне число для гарячої води:")
        return

    await state.update_data(hot_water=hot)
    await message.answer(
        "⚡️ Введіть поточні показники <b>електроенергії (кВт*год)</b>:\n"
        "<i>(Наприклад: <code>1840</code>)</i>",
        parse_mode="HTML"
    )
    await state.set_state(MeterReadingState.waiting_for_electricity)


@router.message(MeterReadingState.waiting_for_electricity, F.text)
async def process_electricity(message: Message, state: FSMContext):
    val_str = message.text.strip().replace(",", ".")
    try:
        elec = float(val_str)
        if elec < 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введіть коректне число для електроенергії:")
        return

    data = await state.get_data()
    cold = data.get("cold_water", 0.0)
    hot = data.get("hot_water", 0.0)
    now = datetime.now()
    telegram_id = message.from_user.id

    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()

        apt_res = await session.execute(select(Apartment).where(Apartment.resident_id == user.id))
        apt = apt_res.scalar_one_or_none()
        apt_id = apt.id if apt else 1
        apt_num = apt.number if apt else 1

        reading = MeterReading(
            apartment_id=apt_id,
            month=now.month,
            year=now.year,
            cold_water=cold,
            hot_water=hot,
            electricity=elec
        )
        session.add(reading)
        await session.commit()

    await state.clear()

    summary_text = (
        f"✅ <b>Показники лічильників успішно збережено!</b>\n\n"
        f"🏢 <b>Квартира:</b> №{apt_num}\n"
        f"📅 <b>Період:</b> {now.strftime('%m/%Y')}\n\n"
        f"🚰 <b>Холодна вода:</b> {cold} м³\n"
        f"♨️ <b>Гаряча вода:</b> {hot} м³\n"
        f"⚡️ <b>Електроенергія:</b> {elec} кВт*год\n\n"
        f"<i>Дані передано до бухгалтерії ОСББ для автоматичного формування платіжок.</i>"
    )
    await message.answer(summary_text, reply_markup=get_main_menu_keyboard(user.role if user else UserRole.RESIDENT), parse_mode="HTML")


# ==========================================
# 3. НОВОСТИ, ОПРОСЫ И ПРОФИЛЬ
# ==========================================

@router.message(F.text.contains("Новини") | F.text.contains("Оголошення"))
async def cmd_announcements(message: Message, state: FSMContext):
    await state.clear()
    async with async_session_maker() as session:
        result = await session.execute(
            select(Announcement).order_by(desc(Announcement.created_at)).limit(5)
        )
        announcements = result.scalars().all()
        
    if not announcements:
        await message.answer("📢 Наразі немає активних оголошень.")
        return
        
    text = "📢 <b>Останні оголошення будинку:</b>\n\n"
    for item in announcements:
        prefix = "🚨 <b>ТЕРМІНОВО:</b> " if item.is_emergency else "📌 "
        date_str = item.created_at.strftime("%d.%m.%Y %H:%M") if item.created_at else ""
        text += f"{prefix}<b>{item.title}</b> <i>({date_str})</i>\n{item.content}\n\n"
        
    await message.answer(text, parse_mode="HTML")


@router.message(F.text.contains("Опитування"))
async def cmd_polls(message: Message, state: FSMContext):
    await state.clear()
    telegram_id = message.from_user.id
    
    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()
        
        polls_res = await session.execute(
            select(Poll).where(Poll.is_active == True).order_by(desc(Poll.created_at))
        )
        polls = polls_res.scalars().all()
        
        if not polls:
            await message.answer("🗳 Наразі немає активних опитувань.")
            return
            
        for poll in polls:
            opts_res = await session.execute(
                select(PollOption).where(PollOption.poll_id == poll.id)
            )
            options = opts_res.scalars().all()
            
            existing_vote = None
            if user:
                vote_res = await session.execute(
                    select(PollVote).where(PollVote.poll_id == poll.id, PollVote.user_id == user.id)
                )
                existing_vote = vote_res.scalar_one_or_none()
            
            poll_text = f"🗳 <b>{poll.title}</b>\n\n{poll.description or ''}\n\n"
            
            kb_buttons = []
            if existing_vote:
                poll_text += "<i>✅ Ви вже проголосували в цьому опитуванні.</i>"
                markup = None
            else:
                for opt in options:
                    kb_buttons.append([
                        InlineKeyboardButton(
                            text=opt.text,
                            callback_data=f"vote_{poll.id}_{opt.id}"
                        )
                    ])
                markup = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
                
            await message.answer(poll_text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data.startswith("vote_"))
async def process_vote(callback: CallbackQuery):
    parts = callback.data.split("_")
    poll_id = int(parts[1])
    option_id = int(parts[2])
    telegram_id = callback.from_user.id
    
    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()
        
        if user:
            exist_vote_res = await session.execute(
                select(PollVote).where(PollVote.poll_id == poll_id, PollVote.user_id == user.id)
            )
            if not exist_vote_res.scalar_one_or_none():
                vote = PollVote(poll_id=poll_id, option_id=option_id, user_id=user.id)
                session.add(vote)
                await session.commit()
        
    await callback.answer("✅ Ваш голос зараховано!")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer("🎉 Дякуємо за участь у житті будинку! Ваш голос збережено.")


@router.message(F.text.contains("Контакти"))
async def cmd_contacts(message: Message, state: FSMContext):
    await state.clear()
    contacts_text = (
        "📞 <b>Важливі контакти нашого будинку:</b>\n\n"
        "🏢 <b>Голова ОСББ:</b>\n"
        "👤 Коваленко Олександр Іванович\n"
        "📱 +380 (67) 123-45-67 (Пн-Пт 09:00 - 18:00)\n\n"
        "🔧 <b>Черговий сантехнік/електрик:</b>\n"
        "📱 +380 (50) 987-65-43\n\n"
        "🚨 <b>Міські аварійні служби:</b>\n"
        "• Аварійна служба (Тепло/Вода): <b>1557</b>\n"
        "• Диспетчер ліфтів: <b>+380 (44) 333-22-11</b>\n"
        "• Екстрені служби: <b>101, 102, 103, 104</b>"
    )
    await message.answer(contacts_text, parse_mode="HTML")


@router.message(F.text.contains("Профіль"))
async def cmd_profile(message: Message, state: FSMContext):
    await state.clear()
    telegram_id = message.from_user.id
    
    async with async_session_maker() as session:
        res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = res.scalar_one_or_none()
        
        if not user:
            await message.answer("⚠️ Будь ласка, спочатку запустіть /start для реєстрації.")
            return
            
        apt_res = await session.execute(select(Apartment).where(Apartment.resident_id == user.id))
        apt = apt_res.scalar_one_or_none()
        
    apt_num = apt.number if apt else "Не прив'язано"
    balance = apt.balance if apt else 0.0
    area = apt.area if apt and apt.area else "Не вказано"
    
    status_emoji = "🟢 Без заборгованостей" if balance >= 0 else f"🔴 Заборгованість: {abs(balance)} грн"
    
    profile_text = (
        f"👤 <b>Особистий профіль мешканця</b>\n\n"
        f"🏷 <b>Ім'я:</b> {user.full_name}\n"
        f"📱 <b>Телефон:</b> {user.phone or 'Не вказано'}\n"
        f"🏢 <b>Квартира:</b> №{apt_num}\n"
        f"📐 <b>Площа:</b> {area} м²\n"
        f"💳 <b>Стан рахунку:</b> {status_emoji}\n\n"
        f"<i>Для перегляду квитанцій скористайтеся кнопкою «📱 Кабінет».</i>"
    )
    
    kb_buttons = [
        [InlineKeyboardButton(text="📋 Мої заявки (статуси та аудіо)", callback_data="resident_my_tickets")],
        [InlineKeyboardButton(text="📊 Подати показники лічильників", callback_data="meters_start")]
    ]
    
    if user.role == UserRole.CONTRACTOR or user.contractor_category:
        kb_buttons.append([InlineKeyboardButton(text="🛠 Панель підрядника (Замовлення)", callback_data="switch_to_contractor")])
    else:
        kb_buttons.append([InlineKeyboardButton(text="💼 Стати підрядником будинку", callback_data="start_register_contractor")])

    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
    await message.answer(profile_text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "resident_profile_back")
async def cb_resident_profile_back(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await cmd_profile(callback.message, state)


@router.callback_query(F.data == "resident_my_tickets")
@router.message(F.text.contains("Мої заявки") | F.text.contains("мої заявки"))
async def cb_resident_my_tickets(event: Message | CallbackQuery):
    if isinstance(event, CallbackQuery):
        await event.answer()
    message = event if isinstance(event, Message) else event.message
    telegram_id = event.from_user.id

    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()
        if not user:
            await message.answer("⚠️ Будь ласка, спочатку запустіть /start для реєстрації.")
            return

        tickets_res = await session.execute(
            select(Ticket).where(Ticket.creator_id == user.id).order_by(desc(Ticket.created_at)).limit(10)
        )
        tickets = tickets_res.scalars().all()

        tickets_data = []
        for t in tickets:
            master_name = None
            if t.assigned_to_id:
                m_res = await session.execute(select(User).where(User.id == t.assigned_to_id))
                m_obj = m_res.scalar_one_or_none()
                if m_obj:
                    master_name = m_obj.full_name
            tickets_data.append((t, master_name))

    if not tickets_data:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 До профілю", callback_data="resident_profile_back")]
            ]
        )
        empty_text = (
            "📋 <b>МОЇ ЗАЯВКИ ДО ПРАВЛІННЯ / ДИСПЕТЧЕРА</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "У вас наразі немає створених заявок на обслуговування.\n\n"
            "<i>Щоб створити нову заявку за допомогою штучного інтелекту або голосу, натисніть кнопку «🔧 Заявка (AI)» у нижньому меню!</i>"
        )
        if isinstance(event, CallbackQuery):
            try:
                await event.message.edit_text(empty_text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                await event.message.answer(empty_text, reply_markup=kb, parse_mode="HTML")
        else:
            await message.answer(empty_text, reply_markup=kb, parse_mode="HTML")
        return

    status_badges = {
        TicketStatus.NEW: "🆕 Нова (на розгляді)",
        TicketStatus.IN_PROGRESS: "🛠 В роботі у майстра",
        TicketStatus.RESOLVED: "✅ Виконано",
        TicketStatus.CANCELLED: "❌ Відхилено"
    }

    if isinstance(event, CallbackQuery):
        try:
            await event.message.delete()
        except Exception:
            pass

    await message.answer(f"📋 <b>Ваші створені заявки ({len(tickets_data)}):</b>\n━━━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML")

    for t, master_name in tickets_data:
        voice_status = "✅ Є аудіо" if t.audio_file_id else "📝 Текст"
        photo_status = "✅ Додано" if t.photo_file_id else "❌ Немає"
        master_line = f"\n👷‍♂️ <b>Призначений майстер:</b> {master_name}" if master_name else ""

        card_text = (
            f"🎫 <b>Заявка №{t.id}</b> [{status_badges.get(t.status, '🛠 В роботі')}]\n"
            f"📅 <b>Дата створення:</b> {t.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"🎙 <b>Аудіо:</b> {voice_status} | 📷 <b>Фото:</b> {photo_status}{master_line}\n\n"
            f"📝 <b>Опис проблеми:</b>\n{t.description}\n"
        )
        if t.ai_summary:
            card_text += f"\n💡 <b>AI підсумок:</b> <i>{t.ai_summary}</i>\n"

        media_row = [
            InlineKeyboardButton(text="📄 Текст заявки", callback_data=f"show_ticket_text_{t.id}"),
            InlineKeyboardButton(text="🎙 Голосове", callback_data=f"show_ticket_voice_{t.id}"),
            InlineKeyboardButton(text="📷 Фото", callback_data=f"show_ticket_photo_{t.id}")
        ]

        kb = InlineKeyboardMarkup(inline_keyboard=[media_row])
        await message.answer(card_text, reply_markup=kb, parse_mode="HTML")


@router.message(F.text.contains("Панель правління"))
async def cmd_admin_menu(message: Message, state: FSMContext):
    await state.clear()
    telegram_id = message.from_user.id
    
    async with async_session_maker() as session:
        res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = res.scalar_one_or_none()
        
        # Если это главный владелец системы из настроек — гарантируем супер-доступ!
        if telegram_id == settings.ADMIN_TELEGRAM_ID:
            if not user:
                user = User(
                    telegram_id=telegram_id,
                    username=message.from_user.username,
                    full_name="Олексій",
                    role=UserRole.SUPER_ADMIN,
                    is_verified=True
                )
                session.add(user)
                await session.commit()
            else:
                user.full_name = "Олексій"
                user.role = UserRole.SUPER_ADMIN
                await session.commit()
        
    if not user or user.role not in (UserRole.ADMIN, UserRole.BOARD, UserRole.SUPER_ADMIN):
        await message.answer("⚠️ Цей розділ доступний лише для членів правління ОСББ.")
        return
        
    await message.answer(
        "🏢 <b>Панель управління ОСББ</b>\n\n"
        "Оберіть потрібну дію з меню нижче:",
        reply_markup=get_admin_panel_keyboard(),
        parse_mode="HTML"
    )
