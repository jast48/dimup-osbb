from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from app.db.session import async_session_maker
from app.db.models import User, Apartment, UserRole
from app.bot.states.user_states import RegistrationState
from app.bot.keyboards.keyboards import (
    get_main_menu_keyboard,
    get_cancel_keyboard,
    get_phone_request_keyboard
)
from app.config import settings

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """
    Точка входа /start: проверяет наличие пользователя в базе.
    Если пользователь новый — запускает пошаговую регистрацию.
    """
    await state.clear()
    telegram_id = message.from_user.id
    
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        
        # Если это главный владелец и его еще нет в новой базе — создаем мгновенно!
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
                
                # Привязываем к квартире 1 по умолчанию
                apt_res = await session.execute(select(Apartment).where(Apartment.number == 1))
                apt = apt_res.scalar_one_or_none()
                if apt:
                    apt.resident_id = user.id
                    await session.commit()
            else:
                user.full_name = "Олексій"
                user.role = UserRole.SUPER_ADMIN
                user.is_verified = True
                await session.commit()
            
        if user:
            # Пользователь уже зарегистрирован
            await message.answer(
                f"👋 Вітаємо, <b>{user.full_name}</b>!\n\n"
                f"🏢 <b>DimUp</b> — цифрова система нашого будинку.\n"
                f"Оберіть потрібний розділ меню нижче:",
                reply_markup=get_main_menu_keyboard(user.role),
                parse_mode="HTML"
            )
        else:
            # Новый пользователь -> запускаем онбординг
            await message.answer(
                "👋 <b>Ласкаво просимо до DimUp!</b>\n\n"
                "Це розумний помічник нашого будинку. Щоб користуватися системою, подавати заявки "
                "та бачити нарахування, пройдіть коротку реєстрацію (це займе 30 секунд).\n\n"
                "🔢 <b>Введіть номер вашої квартири</b> (наприклад: <code>5</code>):",
                reply_markup=get_cancel_keyboard(),
                parse_mode="HTML"
            )
            await state.set_state(RegistrationState.waiting_for_apartment)


@router.message(F.text == "❌ Скасувати")
async def process_cancel(message: Message, state: FSMContext):
    """Отмена текущего действия и возврат в главное меню"""
    await state.clear()
    telegram_id = message.from_user.id
    
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        role = user.role if user else UserRole.RESIDENT
    
    await message.answer(
        "Дію скасовано. Ви повернулися в головне меню.",
        reply_markup=get_main_menu_keyboard(role)
    )


@router.message(RegistrationState.waiting_for_apartment)
async def process_apartment(message: Message, state: FSMContext):
    """Шаг 1: Получение номера квартиры"""
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("⚠️ Будь ласка, введіть тільки число (номер квартири):")
        return
    
    apt_number = int(text)
    await state.update_data(apartment_number=apt_number)
    
    await message.answer(
        f"Чудово, квартира №<b>{apt_number}</b>.\n\n"
        f"👤 Тепер введіть ваше <b>Прізвище та Ім'я</b> (наприклад: <i>Іваненко Петро</i>):",
        parse_mode="HTML"
    )
    await state.set_state(RegistrationState.waiting_for_full_name)


@router.message(RegistrationState.waiting_for_full_name)
async def process_full_name(message: Message, state: FSMContext):
    """Шаг 2: Получение ФИО"""
    full_name = message.text.strip()
    if len(full_name) < 3:
        await message.answer("⚠️ Будь ласка, введіть коректне ім'я та прізвище:")
        return
    
    await state.update_data(full_name=full_name)
    
    await message.answer(
        "📱 Останній крок: поділіться вашим номером телефону для зв'язку з диспетчером у разі аварійних робіт.\n\n"
        "Натисніть кнопку <b>«📱 Поділитися контактом»</b> або введіть номер вручну:",
        reply_markup=get_phone_request_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(RegistrationState.waiting_for_phone)


@router.message(RegistrationState.waiting_for_phone, F.contact | F.text)
async def process_phone(message: Message, state: FSMContext):
    """Шаг 3: Сохранение пользователя и привязка к квартире"""
    phone = message.contact.phone_number if message.contact else message.text.strip()
    data = await state.get_data()
    
    apt_number = data.get("apartment_number")
    full_name = data.get("full_name")
    telegram_id = message.from_user.id
    username = message.from_user.username
    
    # Если это ID админа — сразу делаем ADMIN, иначе RESIDENT
    user_role = UserRole.ADMIN if telegram_id == settings.ADMIN_TELEGRAM_ID else UserRole.RESIDENT
    
    async with async_session_maker() as session:
        # Создаем пользователя
        user = User(
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            phone=phone,
            role=user_role,
            is_verified=True
        )
        session.add(user)
        await session.flush()
        
        # Привязываем к квартире, если она есть
        result = await session.execute(select(Apartment).where(Apartment.number == apt_number))
        apartment = result.scalar_one_or_none()
        if apartment and apartment.resident_id:
            # Квартира уже занята другим жильцом
            await state.clear()
            await message.answer(
                f"⚠️ Квартира №<b>{apt_number}</b> вже зареєстрована за іншим мешканцем.\n"
                "Зверніться до голови ОСББ для вирішення цього питання.",
                parse_mode="HTML"
            )
            return
        if apartment:
            apartment.resident_id = user.id
        else:
            # Создаем квартиру, если еще не было в базе
            new_apt = Apartment(number=apt_number, resident_id=user.id)
            session.add(new_apt)
            
        await session.commit()
    
    await state.clear()
    await message.answer(
        f"🎉 <b>Реєстрацію успішно завершено!</b>\n\n"
        f"Ви закріплені за квартирою №<b>{apt_number}</b>.\n"
        f"Тепер вам доступні всі можливості системи DimUp: створення заявок з AI, перегляд квитанцій та голосування.",
        reply_markup=get_main_menu_keyboard(user_role),
        parse_mode="HTML"
    )
