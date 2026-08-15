from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from app.db.session import async_session_maker
from app.db.models import User, Apartment, ServiceOrder, ServiceOrderStatus, UserRole
from app.bot.states.user_states import StatesGroup, State
from app.bot.keyboards.keyboards import get_main_menu_keyboard, get_cancel_keyboard

router = Router()

class MarketplaceOrderState(StatesGroup):
    waiting_for_time = State()
    waiting_for_comment = State()
    waiting_for_phone = State()

# Каталог проверенных услуг
MARKETPLACE_CATALOG = {
    "plumbing_tap": {
        "title": "Заміна / ремонт змішувача чи крану",
        "category": "Сантехніка",
        "price": 350.0,
        "desc": "Демонтаж старого змішувача, підключення нового, перевірка герметичності."
    },
    "plumbing_boiler": {
        "title": "Монтаж або чистка бойлера",
        "category": "Сантехніка",
        "price": 650.0,
        "desc": "Підключення до водопроводу, електрики, заміна аноду та промивка баку."
    },
    "plumbing_clog": {
        "title": "Прочистка каналізації / сифону",
        "category": "Сантехніка",
        "price": 400.0,
        "desc": "Усунення засмічень у ванній чи кухні спеціальним обладнанням."
    },
    "elec_sockets": {
        "title": "Заміна розеток та вимикачів",
        "category": "Електрика",
        "price": 180.0,
        "desc": "Безпечна заміна фурнітури, перевірка напруги та контактів."
    },
    "elec_light": {
        "title": "Монтаж люстри / світильника",
        "category": "Електрика",
        "price": 350.0,
        "desc": "Надійне кріплення до стелі, підключення проводки, тестування режимів."
    },
    "elec_relay": {
        "title": "Встановлення реле напруги (Зубр)",
        "category": "Електрика",
        "price": 550.0,
        "desc": "Монтаж у щиток для захисту побутової техніки від стрибків напруги."
    },
    "clean_general": {
        "title": "Генеральне прибирання квартири",
        "category": "Клінінг",
        "price": 1200.0,
        "desc": "Комплексне миття поверхонь, санвузлів, кухні професійними засобами."
    },
    "clean_windows": {
        "title": "Миття вікон та балконів",
        "category": "Клінінг",
        "price": 450.0,
        "desc": "Миття скла з двох сторін, рам, підвіконь та москітних сіток."
    },
    "ac_clean": {
        "title": "Чистка та дезінфекція кондиціонера",
        "category": "Клімат",
        "price": 600.0,
        "desc": "Антибактеріальна обробка теплообмінника, фільтрів та турбіни."
    },
    "lock_replace": {
        "title": "Заміна замка або серцевини дверей",
        "category": "Безпека",
        "price": 450.0,
        "desc": "Підбір та монтаж нового зламостійкого замка або серцевини."
    }
}


@router.message(F.text.contains("Маркетплейс") | F.text.contains("Послуги"))
async def cmd_marketplace_main(message: Message, state: FSMContext):
    """Главный каталог проверенных услуг для дома"""
    await state.clear()
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🚰 Сантехнічні роботи", callback_data="mkt_cat_plumbing"),
                InlineKeyboardButton(text="💡 Електрика", callback_data="mkt_cat_elec")
            ],
            [
                InlineKeyboardButton(text="🧹 Клінінг та чистота", callback_data="mkt_cat_clean"),
                InlineKeyboardButton(text="❄️ Кондиціонери", callback_data="mkt_cat_ac")
            ],
            [
                InlineKeyboardButton(text="🔑 Замки та двері", callback_data="mkt_cat_lock")
            ]
        ]
    )

    text = (
        "🛠 <b>Маркетплейс перевірених послуг DimUp</b>\n\n"
        "Замовляйте послуги акредитованих майстрів будинку з гарантією якості та фіксованими цінами:\n\n"
        "• <b>Перевірені майстри</b> з рейтингом мешканців\n"
        "• <b>Зручний час</b> візиту\n"
        "• <b>Оплата карткою або готівкою</b> після виконання\n\n"
        "Оберіть категорію робіт нижче:"
    )
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("mkt_cat_"))
async def cb_show_category(callback: CallbackQuery):
    cat_code = callback.data.replace("mkt_cat_", "")
    
    buttons = []
    for code, item in MARKETPLACE_CATALOG.items():
        if code.startswith(cat_code):
            buttons.append([
                InlineKeyboardButton(
                    text=f"{item['title']} — від {int(item['price'])} грн",
                    callback_data=f"mkt_item_{code}"
                )
            ])
            
    buttons.append([InlineKeyboardButton(text="🔙 Назад до категорій", callback_data="mkt_back_main")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(
        "🛠 <b>Оберіть потрібну послугу:</b>\n<i>Натисніть на послугу для перегляду деталей та замовлення майстра:</i>",
        reply_markup=kb,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "mkt_back_main")
async def cb_back_to_market(callback: CallbackQuery):
    await callback.message.delete()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🚰 Сантехнічні роботи", callback_data="mkt_cat_plumbing"),
                InlineKeyboardButton(text="💡 Електрика", callback_data="mkt_cat_elec")
            ],
            [
                InlineKeyboardButton(text="🧹 Клінінг та чистота", callback_data="mkt_cat_clean"),
                InlineKeyboardButton(text="❄️ Кондиціонери", callback_data="mkt_cat_ac")
            ],
            [
                InlineKeyboardButton(text="🔑 Замки та двері", callback_data="mkt_cat_lock")
            ]
        ]
    )
    await callback.message.answer(
        "🛠 <b>Маркетплейс перевірених послуг DimUp</b>\n\nОберіть категорію:",
        reply_markup=kb,
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("mkt_item_"))
async def cb_show_item_details(callback: CallbackQuery, state: FSMContext):
    item_code = callback.data.replace("mkt_item_", "")
    item = MARKETPLACE_CATALOG.get(item_code)
    if not item:
        await callback.answer("Послугу не знайдено.")
        return

    await state.update_data(item_code=item_code, item_title=item["title"], item_price=item["price"])

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Замовити майстра", callback_data="mkt_order_start")
            ],
            [
                InlineKeyboardButton(text="🔙 До каталогу", callback_data="mkt_back_main")
            ]
        ]
    )

    text = (
        f"🏷 <b>{item['title']}</b>\n"
        f"📂 Категорія: <b>{item['category']}</b>\n"
        f"💰 Орієнтовна вартість: <b>від {int(item['price'])} грн</b>\n\n"
        f"📝 <b>Опис послуги:</b>\n{item['desc']}\n\n"
        f"<i>Бажаєте викликати спеціаліста на зручний час?</i>"
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "mkt_order_start")
async def cb_start_order(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    title = data.get("item_title", "Послуга")
    
    await callback.message.delete()
    await callback.message.answer(
        f"📅 <b>Замовлення послуги: «{title}»</b>\n\n"
        f"Вкажіть <b>бажану дату та час візиту майстра</b>:\n"
        f"<i>(Наприклад: «Завтра після 15:00» або «Субота 11:00»)</i>",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(MarketplaceOrderState.waiting_for_time)


@router.message(MarketplaceOrderState.waiting_for_time, F.text)
async def process_order_time(message: Message, state: FSMContext):
    pref_time = message.text.strip()
    await state.update_data(preferred_time=pref_time)
    
    await message.answer(
        "📝 Додайте <b>коментар або уточнення до замовлення</b> (або відправте «-»):",
        parse_mode="HTML"
    )
    await state.set_state(MarketplaceOrderState.waiting_for_comment)


@router.message(MarketplaceOrderState.waiting_for_comment, F.text)
async def process_order_comment(message: Message, state: FSMContext, bot: Bot):
    comment = message.text.strip()
    if comment == "-":
        comment = None

    data = await state.get_data()
    title = data.get("item_title")
    price = data.get("item_price", 0.0)
    pref_time = data.get("preferred_time")
    telegram_id = message.from_user.id

    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()

        apt_res = await session.execute(select(Apartment).where(Apartment.resident_id == user.id))
        apt = apt_res.scalar_one_or_none()
        apt_num = apt.number if apt else "—"

        order = ServiceOrder(
            user_id=user.id,
            apartment_id=apt.id if apt else None,
            service_title=title,
            price_est=price,
            preferred_time=pref_time,
            contact_phone=user.phone,
            comment=comment,
            status=ServiceOrderStatus.PENDING
        )
        session.add(order)
        await session.commit()
        order_id = order.id

    await state.clear()

    confirm_text = (
        f"🎉 <b>Замовлення №{order_id} успішно прийнято!</b>\n\n"
        f"🛠 <b>Послуга:</b> {title}\n"
        f"💰 <b>Орієнтовна вартість:</b> від {price:.2f} грн\n"
        f"⏰ <b>Бажаний час:</b> {pref_time}\n"
        f"🏢 <b>Квартира:</b> №{apt_num}\n\n"
        f"<i>Диспетчер зв'яжеться з вами для підтвердження деталей та призначить майстра.</i>"
    )
    await message.answer(confirm_text, reply_markup=get_main_menu_keyboard(user.role), parse_mode="HTML")
