from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo
)
from app.config import settings
from app.db.models import UserRole

def get_contractor_menu_keyboard() -> ReplyKeyboardMarkup:
    """Нижня клавіатура для підрядника / майстра"""
    keyboard = [
        [
            KeyboardButton(text="📥 Нові замовлення"),
            KeyboardButton(text="📋 Мої активні роботи")
        ],
        [
            KeyboardButton(text="⭐️ Рейтинг та відгуки"),
            KeyboardButton(text="⚙️ Профіль майстра")
        ],
        [
            KeyboardButton(text="🏠 Режим мешканця")
        ]
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True
    )


def get_main_menu_keyboard(role: UserRole = UserRole.RESIDENT) -> ReplyKeyboardMarkup:
    """Компактная нижняя клавиатура"""
    if role == UserRole.CONTRACTOR:
        return get_contractor_menu_keyboard()

    keyboard = [
        [
            KeyboardButton(text="🔧 Заявка (AI)"),
            KeyboardButton(text="🤖 AI-Консьєрж"),
            KeyboardButton(text="📱 Кабінет")
        ],
        [
            KeyboardButton(text="💳 Рахунки / Оплата"),
            KeyboardButton(text="🛠 Послуги майстрів"),
            KeyboardButton(text="🗳 Опитування")
        ],
        [
            KeyboardButton(text="📢 Новини"),
            KeyboardButton(text="👤 Профіль")
        ]
    ]

    if role in (UserRole.ADMIN, UserRole.BOARD, UserRole.SUPER_ADMIN):
        keyboard.append([KeyboardButton(text="🏢 Панель правління")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True
    )

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Скасувати")]],
        resize_keyboard=True
    )

def get_phone_request_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Поділитися контактом", request_contact=True)],
            [KeyboardButton(text="❌ Скасувати")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_ticket_photo_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Пропустити фото", callback_data="skip_photo")],
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel_ticket")]
        ]
    )

def get_ticket_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Відправити заявку", callback_data="confirm_ticket_send"),
                InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel_ticket")
            ]
        ]
    )

def get_admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Инлайн-меню панели управления председателя"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🛠 Активні заявки", callback_data="admin_tickets_list"),
                InlineKeyboardButton(text="📦 Архів заявок", callback_data="admin_tickets_archive")
            ],
            [
                InlineKeyboardButton(text="⚖️ Боржники та претензії", callback_data="admin_debt_claims_menu"),
                InlineKeyboardButton(text="🏦 Імпорт виписки банку", callback_data="admin_bank_sync_menu")
            ],
            [
                InlineKeyboardButton(text="💰 Виставити рахунок", callback_data="admin_create_bill"),
                InlineKeyboardButton(text="📢 AI-Розсилка", callback_data="admin_ai_broadcast_start")
            ],
            [
                InlineKeyboardButton(text="🗳 Опитування (Закон №417)", callback_data="admin_polls_menu"),
                InlineKeyboardButton(text="👥 Мешканці", callback_data="admin_residents")
            ],
            [
                InlineKeyboardButton(text="👷‍♂️ Реєстр майстрів", callback_data="admin_contractors_list"),
                InlineKeyboardButton(text="🔙 Назад до меню", callback_data="admin_back_main")
            ]
        ]
    )
