import io
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from app.db.session import async_session_maker
from app.db.models import User, Apartment, Ticket, TicketCategory, TicketUrgency, TicketStatus
from app.bot.states.user_states import TicketState
from app.bot.keyboards.keyboards import (
    get_main_menu_keyboard,
    get_cancel_keyboard,
    get_ticket_photo_keyboard,
    get_ticket_confirm_keyboard
)
from app.config import settings
from app.services.ai_service import AIService

router = Router()

CATEGORY_NAMES = {
    TicketCategory.PLUMBING: "🚰 Сантехніка / Вода",
    TicketCategory.ELECTRICITY: "💡 Електрика / Освітлення",
    TicketCategory.ELEVATOR: "🛗 Ліфтове обладнання",
    TicketCategory.CLEANING: "🧹 Прибирання та чистота",
    TicketCategory.SECURITY: "🚪 Домофон / Ворота / Безпека",
    TicketCategory.ROOF_FACADE: "🏢 Дах / Фасад / Під'їзд",
    TicketCategory.OTHER: "📌 Інше господарське питання"
}

URGENCY_NAMES = {
    TicketUrgency.EMERGENCY: "🚨 Аварійна (потрібне термінове реагування!)",
    TicketUrgency.NORMAL: "🟡 Звичайна (в порядку черги)",
    TicketUrgency.LOW: "🟢 Нетермінова (планова)"
}

@router.message(F.text.contains("Заявка"))
async def cmd_new_ticket(message: Message, state: FSMContext):
    """Начало создания заявки"""
    await state.clear()
    telegram_id = message.from_user.id
    
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        
        if not user:
            await message.answer("⚠️ Будь ласка, спочатку запустіть /start для реєстрації.")
            return

    await message.answer(
        "🔧 <b>Створення нової заявки на обслуговування</b>\n\n"
        "Опишіть вашу проблему текстом <b>або надиктуйте голосовим повідомленням 🎙</b>:\n"
        "<i>(Наприклад: «На 4 поверсі не горить лампа» або надішліть аудіозапис)</i>\n\n"
        "Штучний інтелект <b>DimUp AI</b> автоматично визначить терміновість та категорію майстра.",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(TicketState.waiting_for_description)


@router.message(TicketState.waiting_for_description, F.text | F.voice | F.photo)
async def process_ticket_description(message: Message, state: FSMContext, bot: Bot):
    """Обработка текста, голосового сообщения или прямого фото жильца"""
    loading_msg = await message.answer("🤖 <i>AI аналізує ваше звернення...</i>", parse_mode="HTML")
    
    recognized_text = ""
    audio_file_id = None
    photo_file_id = None

    if message.voice:
        # Голосовое сообщение
        audio_file_id = message.voice.file_id
        voice_file = await bot.get_file(audio_file_id)
        voice_stream = io.BytesIO()
        await bot.download_file(voice_file.file_path, destination=voice_stream)
        audio_bytes = voice_stream.getvalue()

        ai_res = await AIService.classify_ticket(audio_bytes=audio_bytes, audio_mime_type="audio/ogg")
        recognized_text = ai_res.get("recognized_text") or "Голосове повідомлення"
    elif message.photo:
        # Прямое фото с подписью или без
        photo_file_id = message.photo[-1].file_id
        caption = message.caption.strip() if message.caption else "Фото поломки в будинку"
        recognized_text = caption

        photo_file = await bot.get_file(photo_file_id)
        photo_stream = io.BytesIO()
        await bot.download_file(photo_file.file_path, destination=photo_stream)
        image_bytes = photo_stream.getvalue()

        ai_res = await AIService.classify_ticket(description=caption, image_bytes=image_bytes)
    else:
        # Текстовое сообщение
        description = message.text.strip()
        recognized_text = description
        ai_res = await AIService.classify_ticket(description=description)

    await loading_msg.delete()

    category_str = ai_res.get("category", "other")
    urgency_str = ai_res.get("urgency", "normal")
    advice = ai_res.get("recommended_action", "Заявка прийнята.")
    
    try:
        category = TicketCategory(category_str)
    except ValueError:
        category = TicketCategory.OTHER
        
    try:
        urgency = TicketUrgency(urgency_str)
    except ValueError:
        urgency = TicketUrgency.NORMAL

    # Сохраняем в состояние FSM
    await state.update_data(
        description=recognized_text,
        category=category.value,
        urgency=urgency.value,
        ai_summary=advice,
        photo_file_id=photo_file_id,
        audio_file_id=audio_file_id
    )

    voice_badge = "🎙 <i>(Розпізнано з вашого голосу)</i>\n" if message.voice else ""
    photo_badge = "📷 <i>(Фото успішно прикріплено)</i>\n" if photo_file_id else ""

    text = (
        f"💡 <b>Результат AI-аналізу вашої заявки:</b>\n\n"
        f"{voice_badge}{photo_badge}"
        f"📝 <b>Опис:</b> {recognized_text}\n"
        f"📂 <b>Категорія:</b> {CATEGORY_NAMES.get(category)}\n"
        f"⚡️ <b>Срочність:</b> {URGENCY_NAMES.get(urgency)}\n\n"
        f"🤖 <b>Порада від AI:</b>\n<i>{advice}</i>\n\n"
    )

    if photo_file_id:
        text += "Надіслати заявку до диспетчерської служби?"
        await message.answer(text, reply_markup=get_ticket_confirm_keyboard(), parse_mode="HTML")
        await state.set_state(TicketState.confirming_ticket)
    else:
        text += "📷 Бажаєте додати <b>фото поломки</b>? (Надішліть фото або натисніть «Пропустити фото»):"
        await message.answer(text, reply_markup=get_ticket_photo_keyboard(), parse_mode="HTML")
        await state.set_state(TicketState.waiting_for_photo)


@router.message(TicketState.waiting_for_photo, F.photo)
async def process_ticket_photo(message: Message, state: FSMContext):
    """Обработка фото поломки"""
    photo_id = message.photo[-1].file_id
    await state.update_data(photo_file_id=photo_id)
    
    await message.answer(
        "📷 Фото успішно додано!\n\nНадіслати заявку до диспетчерської служби?",
        reply_markup=get_ticket_confirm_keyboard()
    )
    await state.set_state(TicketState.confirming_ticket)


@router.callback_query(TicketState.waiting_for_photo, F.data == "skip_photo")
async def process_skip_photo(callback: CallbackQuery, state: FSMContext):
    """Пропуск фото"""
    await callback.message.delete()
    await callback.message.answer(
        "Надіслати заявку до диспетчерської служби?",
        reply_markup=get_ticket_confirm_keyboard()
    )
    await state.set_state(TicketState.confirming_ticket)


@router.callback_query(TicketState.confirming_ticket, F.data == "confirm_ticket_send")
async def process_ticket_confirmation(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Финальное сохранение заявки в БД"""
    data = await state.get_data()
    telegram_id = callback.from_user.id
    
    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()
        
        apt_res = await session.execute(select(Apartment).where(Apartment.resident_id == user.id))
        apt = apt_res.scalar_one_or_none()
        
        ticket = Ticket(
            creator_id=user.id,
            apartment_id=apt.id if apt else None,
            category=TicketCategory(data.get("category", "other")),
            urgency=TicketUrgency(data.get("urgency", "normal")),
            description=data.get("description", ""),
            ai_summary=data.get("ai_summary", ""),
            photo_file_id=data.get("photo_file_id"),
            audio_file_id=data.get("audio_file_id"),
            status=TicketStatus.NEW
        )
        session.add(ticket)
        await session.commit()
        ticket_id = ticket.id
        apt_num = apt.number if apt else "—"

    # Мгновенное оповещение председателя / диспетчера
    admin_media_row = [
        InlineKeyboardButton(text="📄 Текст заявки", callback_data=f"show_ticket_text_{ticket_id}")
    ]
    if data.get("audio_file_id"):
        admin_media_row.append(InlineKeyboardButton(text="🎙 Голосове", callback_data=f"show_ticket_voice_{ticket_id}"))
    if data.get("photo_file_id"):
        admin_media_row.append(InlineKeyboardButton(text="📷 Фото", callback_data=f"show_ticket_photo_{ticket_id}"))

    admin_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            admin_media_row,
            [
                InlineKeyboardButton(text="👷‍♂️ Призначити майстра", callback_data=f"assign_master_ticket_{ticket_id}"),
                InlineKeyboardButton(text="🛠 В роботу", callback_data=f"set_status_{ticket_id}_in_progress")
            ],
            [
                InlineKeyboardButton(text="✅ Виконано", callback_data=f"set_status_{ticket_id}_resolved"),
                InlineKeyboardButton(text="❌ Відхилити", callback_data=f"set_status_{ticket_id}_cancelled")
            ]
        ]
    )

    admin_notify_text = (
        f"🚨 <b>НОВА ЗАЯВКА №{ticket_id} ВІД МЕШКАНЦЯ!</b>\n\n"
        f"👤 <b>Мешканець:</b> {user.full_name} (Кв. №{apt_num})\n"
        f"📱 <b>Тел:</b> {user.phone or '—'}\n"
        f"📂 <b>Категорія:</b> {CATEGORY_NAMES.get(ticket.category)}\n"
        f"⚡️ <b>Срочність:</b> {URGENCY_NAMES.get(ticket.urgency)}\n\n"
        f"📝 <b>Текст:</b> {ticket.description}\n"
        f"💡 <b>AI порада:</b> <i>{ticket.ai_summary or '—'}</i>"
    )
    try:
        await bot.send_message(
            settings.ADMIN_TELEGRAM_ID,
            admin_notify_text,
            reply_markup=admin_kb,
            parse_mode="HTML"
        )
    except Exception:
        pass

    await state.clear()
    await callback.message.delete()
    
    user_media_row = [
        InlineKeyboardButton(text="📄 Текст заявки", callback_data=f"show_ticket_text_{ticket_id}")
    ]
    if data.get("audio_file_id"):
        user_media_row.append(InlineKeyboardButton(text="🎙 Моє голосове", callback_data=f"show_ticket_voice_{ticket_id}"))
    if data.get("photo_file_id"):
        user_media_row.append(InlineKeyboardButton(text="📷 Моє фото", callback_data=f"show_ticket_photo_{ticket_id}"))

    user_kb = InlineKeyboardMarkup(inline_keyboard=[user_media_row])

    success_text = (
        f"✅ <b>Заявку №{ticket_id} успішно зареєстровано!</b>\n\n"
        f"Вона передана черговому майстру та голові ОСББ.\n"
        f"Ви отримуватимете автоматичні сповіщення при зміні її статусу."
    )
    await callback.message.answer(success_text, reply_markup=user_kb, parse_mode="HTML")


@router.callback_query(F.data == "cancel_ticket")
async def process_ticket_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("❌ Створення заявки скасовано.", reply_markup=get_main_menu_keyboard())


# ==========================================
# ОЦЕНКА КАЧЕСТВА РАБОТЫ (1-5 ЗВЕЗД)
# ==========================================

@router.callback_query(F.data.startswith("rate_ticket_"))
async def process_ticket_rating(callback: CallbackQuery):
    """Сохранение оценки от жильца"""
    parts = callback.data.split("_")
    ticket_id = int(parts[2])
    rating_stars = int(parts[3])

    async with async_session_maker() as session:
        res = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = res.scalar_one_or_none()
        if ticket:
            ticket.rating = rating_stars
            await session.commit()

    stars_str = "⭐" * rating_stars
    await callback.answer(f"Дякуємо! Ваша оцінка: {stars_str}")
    try:
        await callback.message.edit_text(
            f"🎉 <b>Дякуємо за вашу оцінку ({stars_str})!</b>\n"
            f"Ваш відгук допомагає покращувати якість обслуговування нашого будинку.",
            parse_mode="HTML"
        )
    except Exception:
        pass
