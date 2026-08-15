from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from app.db.session import async_session_maker
from app.db.models import User
from app.bot.states.user_states import ConciergeState
from app.bot.keyboards.keyboards import get_main_menu_keyboard, get_cancel_keyboard
from app.services.ai_service import AIService

router = Router()

@router.message(F.text.contains("Консьєрж"))
async def cmd_concierge_start(message: Message, state: FSMContext):
    """Вход в режим диалога с AI-Консьержем"""
    await state.clear()
    await message.answer(
        "🤖 <b>Вітаю! Я — ваш цілодобовий AI-Консьєрж.</b>\n\n"
        "Я знаю все про наш будинок:\n"
        "• Графіки вивозу сміття та прибирання\n"
        "• Правила проведення ремонтних робіт та режим тиші\n"
        "• Тарифи ОСББ та контакти аварійних служб\n\n"
        "💬 <b>Задайте будь-яке питання</b> (наприклад: <i>«Коли можна шуміти та робити ремонт?»</i> або <i>«Який у нас тариф?»</i>):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(ConciergeState.in_dialog)


@router.message(ConciergeState.in_dialog, F.text)
async def process_concierge_question(message: Message, state: FSMContext):
    """Обработка вопроса к AI"""
    question = message.text.strip()
    telegram_id = message.from_user.id
    
    # Получаем имя жителя для персонализированного ответа
    resident_name = "Мешканець"
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user:
            resident_name = user.full_name
            
    # Отправляем индикатор набора сообщения
    loading_msg = await message.answer("🤖 <i>Шукаю відповідь у базі знань будинку...</i>", parse_mode="HTML")
    
    answer = await AIService.ask_concierge(question, resident_name=resident_name)
    
    await loading_msg.delete()
    await message.answer(
        f"🤖 <b>AI-Консьєрж:</b>\n\n{answer}\n\n"
        f"<i>Ви можете задати наступне питання або натиснути «❌ Скасувати» для повернення в меню.</i>",
        parse_mode="HTML"
    )
