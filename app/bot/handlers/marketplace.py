from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, desc
from app.db.session import async_session_maker
from app.db.models import User, Apartment, ServiceOrder, ServiceOrderStatus, UserRole
from app.bot.states.user_states import StatesGroup, State
from app.bot.keyboards.keyboards import get_main_menu_keyboard, get_cancel_keyboard

router = Router()


class MarketplaceOrderState(StatesGroup):
    waiting_for_time = State()
    waiting_for_comment = State()
    waiting_for_phone = State()


# ==========================================
# 1. БАЗА ПЕРЕВІРЕНИХ ПІДРЯДНИКІВ ТА МАЙСТРІВ
# ==========================================

CONTRACTORS_CATALOG = {
    "plumbing": {
        "name": "Олексій Коваленко",
        "company": "ФОП Коваленко (Сантехсервіс)",
        "category": "🚰 Сантехнічні роботи",
        "rating": 4.98,
        "reviews_count": 142,
        "experience": "9 років досвіду",
        "badge": "🥇 Топ майстер будинку",
        "phone": "+380 67 123-45-67",
        "desc": "Заміна труб, змішувачів, сифонів, монтаж та чистка бойлерів, усунення складних протікань та аварійних засмічень.",
        "services": [
            ("plumbing_tap", "Заміна змішувача / крану", 350.0),
            ("plumbing_boiler", "Монтаж або чистка бойлера", 650.0),
            ("plumbing_clog", "Прочистка каналізації", 400.0),
            ("plumbing_toilet", "Ремонт інсталяції / унітазу", 450.0)
        ]
    },
    "electricity": {
        "name": "Сергій Мельник",
        "company": "ЕлектроСервіс Про",
        "category": "💡 Електромонтаж",
        "rating": 4.95,
        "reviews_count": 98,
        "experience": "11 років досвіду",
        "badge": "⚡️ 5-й розряд допуску",
        "phone": "+380 50 234-56-78",
        "desc": "Повна заміна проводки, монтаж люстр, світильників, щитків, реле напруги Зубр, пошук коротких замикань.",
        "services": [
            ("elec_sockets", "Заміна розеток та вимикачів", 180.0),
            ("elec_light", "Монтаж люстри / світильника", 350.0),
            ("elec_relay", "Встановлення реле напруги (Зубр)", 550.0),
            ("elec_panel", "Збірка / діагностика щитка", 800.0)
        ]
    },
    "cleaning": {
        "name": "Служба «Чистий Дім»",
        "company": "ТОВ «Клінінг Сервіс Груп»",
        "category": "🧹 Професійний клінінг",
        "rating": 4.92,
        "reviews_count": 85,
        "experience": "5 років на ринку",
        "badge": "🌿 Еко-засоби Kärcher",
        "phone": "+380 63 345-67-89",
        "desc": "Генеральне та підтримуюче прибирання, миття вікон, хімчистка м'яких меблів та килимів прямо в квартирі.",
        "services": [
            ("clean_general", "Генеральне прибирання квартири", 1200.0),
            ("clean_windows", "Миття вікон та балконів", 450.0),
            ("clean_sofa", "Хімчистка дивану / матрацу", 700.0),
            ("clean_post_renov", "Прибирання після ремонту", 1800.0)
        ]
    },
    "ac": {
        "name": "Артем Шевчук",
        "company": "ТОВ «Аква-Клімат»",
        "category": "❄️ Кондиціонери та вентиляція",
        "rating": 4.97,
        "reviews_count": 64,
        "experience": "7 років досвіду",
        "badge": "🛡 Офіційна гарантія 12 міс",
        "phone": "+380 97 456-78-90",
        "desc": "Монтаж, антибактеріальна чистка, дозаправка фреоном R410/R32, ремонт плат управління та компресорів.",
        "services": [
            ("ac_clean", "Чистка та дезінфекція спліт-системи", 600.0),
            ("ac_freon", "Дозаправка фреоном", 500.0),
            ("ac_install", "Монтаж кондиціонера", 2500.0)
        ]
    },
    "locks": {
        "name": "Віталій Бондар",
        "company": "Майстерня «Замковий Захист»",
        "category": "🔑 Замки, двері та безпека",
        "rating": 5.0,
        "reviews_count": 52,
        "experience": "14 років досвіду",
        "badge": "🚨 Терміновий виїзд за 20 хв",
        "phone": "+380 68 567-89-01",
        "desc": "Аварійне відкриття без пошкоджень, заміна та врізка броньованих замків Mottura, Mul-T-Lock, регулювання петель.",
        "services": [
            ("lock_replace", "Заміна замка або серцевини", 450.0),
            ("lock_open", "Аварійне відкриття дверей", 700.0),
            ("door_adjust", "Регулювання вхідних дверей", 350.0)
        ]
    },
    "logistics": {
        "name": "DimUp Експрес Вантаж",
        "company": "Логістична служба будинку",
        "category": "🚚 Вантажники та перевезення",
        "rating": 4.90,
        "reviews_count": 73,
        "experience": "6 років досвіду",
        "badge": "📦 Власний автопарк",
        "phone": "+380 93 678-90-12",
        "desc": "Перевезення меблів, підйом будматеріалів на поверх, вивіз будівельного сміття у спеціальні контейнери.",
        "services": [
            ("log_delivery", "Доставка та підйом на поверх", 400.0),
            ("log_trash", "Вивіз будівельного сміття (бус)", 1200.0),
            ("log_movers", "Послуги вантажників (2 ос. / год)", 500.0)
        ]
    }
}


# ==========================================
# 2. ГОЛОВНЕ МЕНЮ МАРКЕТПЛЕЙСУ
# ==========================================

@router.message(Command("services"))
@router.message(Command("marketplace"))
@router.message(F.text.contains("Маркетплейс") | F.text.contains("Послуги") | F.text.contains("майстрів"))
async def cmd_marketplace_main(message: Message, state: FSMContext):
    """Головне меню маркетплейсу послуг та підрядників"""
    await state.clear()
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👷‍♂️ Перевірені підрядники будинку", callback_data="mkt_contractors_list")
            ],
            [
                InlineKeyboardButton(text="🚰 Сантехніка", callback_data="mkt_cat_plumbing"),
                InlineKeyboardButton(text="💡 Електрика", callback_data="mkt_cat_electricity")
            ],
            [
                InlineKeyboardButton(text="🧹 Клінінг", callback_data="mkt_cat_cleaning"),
                InlineKeyboardButton(text="❄️ Кондиціонери", callback_data="mkt_cat_ac")
            ],
            [
                InlineKeyboardButton(text="🔑 Замки та двері", callback_data="mkt_cat_locks"),
                InlineKeyboardButton(text="🚚 Вантажники / Вивіз", callback_data="mkt_cat_logistics")
            ],
            [
                InlineKeyboardButton(text="📦 Мої замовлення", callback_data="mkt_my_orders")
            ]
        ]
    )

    text = (
        "🛠 <b>МАРКЕТПЛЕЙС ПОСЛУГ ТА ПІДРЯДНИКІВ DimUp</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Замовляйте послуги акредитованих майстрів будинку з фіксованими цінами та гарантією якості:\n\n"
        "⭐️ <b>Перевірені майстри:</b> рейтинг на основі відгуків реальних сусідів\n"
        "🛡 <b>Гарантія безпеки:</b> всі підрядники верифіковані правлінням ОСББ\n"
        "⏰ <b>Зручний вибір часу:</b> майстер приходить точно у погоджену годину\n"
        "💳 <b>Оплата за фактом:</b> карткою або готівкою після перевірки робіт\n\n"
        "Оберіть потрібний розділ нижче:"
    )
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


# ==========================================
# 3. СПИСОК ПЕРЕВІРЕНИХ ПІДРЯДНИКІВ
# ==========================================

@router.callback_query(F.data == "mkt_contractors_list")
async def cb_contractors_list(callback: CallbackQuery):
    await callback.answer()
    
    buttons = []
    for cat_key, c in CONTRACTORS_CATALOG.items():
        buttons.append([
            InlineKeyboardButton(
                text=f"{c['category'].split(' ')[0]} {c['name']} (⭐ {c['rating']})",
                callback_data=f"mkt_contractor_view_{cat_key}"
            )
        ])
        
    buttons.append([InlineKeyboardButton(text="🔙 Назад до меню", callback_data="mkt_main_hub")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    text = (
        "👷‍♂️ <b>РЕЄСТР ПЕРЕВІРЕНИХ ПІДРЯДНИКІВ БУДИНКУ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Усі спеціалісти пройшли перевірку документів, мають високий рейтинг задоволеності мешканців та несуть гарантійні зобов'язання.\n\n"
        "<i>Оберіть майстра, щоб переглянути анкету, відгуки та викликати:</i>"
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("mkt_contractor_view_"))
async def cb_view_contractor(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    cat_key = callback.data.replace("mkt_contractor_view_", "")
    c = CONTRACTORS_CATALOG.get(cat_key)
    if not c:
        await callback.answer("Підрядника не знайдено.")
        return

    buttons = []
    for s_code, s_title, s_price in c["services"]:
        buttons.append([
            InlineKeyboardButton(
                text=f"➕ {s_title} (від {int(s_price)} грн)",
                callback_data=f"mkt_item_direct_{cat_key}_{s_code}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text=f"📞 Зателефонувати майстру",
            url=f"https://t.me/share/url?url=Замовлення%20послуги%20в%20ОСББ"
        )
    ])
    buttons.append([InlineKeyboardButton(text="🔙 До списку підрядників", callback_data="mkt_contractors_list")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    text = (
        f"👤 <b>{c['name']}</b>\n"
        f"🏢 <b>{c['company']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Спеціалізація:</b> {c['category']}\n"
        f"⭐️ <b>Рейтинг:</b> <b>{c['rating']} / 5.0</b> ({c['reviews_count']} виконаних замовлень)\n"
        f"⏳ <b>Досвід роботи:</b> {c['experience']}\n"
        f"🎖 <b>Статус:</b> {c['badge']}\n\n"
        f"📝 <b>Про майстра:</b>\n{c['desc']}\n\n"
        f"📋 <b>Популярні послуги майстра:</b>"
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


# ==========================================
# 4. ПЕРЕГЛЯД КАТЕГОРІЙ ПОСЛУГ
# ==========================================

@router.callback_query(F.data.startswith("mkt_cat_"))
async def cb_show_category(callback: CallbackQuery):
    await callback.answer()
    cat_code = callback.data.replace("mkt_cat_", "")
    c = CONTRACTORS_CATALOG.get(cat_code)
    
    if not c:
        await callback.answer("Категорію не знайдено.")
        return

    buttons = []
    for s_code, s_title, s_price in c["services"]:
        buttons.append([
            InlineKeyboardButton(
                text=f"{s_title} — від {int(s_price)} грн",
                callback_data=f"mkt_item_direct_{cat_code}_{s_code}"
            )
        ])
        
    buttons.append([InlineKeyboardButton(text="🔙 Назад до каталогу", callback_data="mkt_main_hub")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    text = (
        f"{c['category']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👷‍♂️ <b>Закріплений майстер:</b> {c['name']} (⭐ {c['rating']})\n\n"
        f"<i>Оберіть потрібну послугу для оформлення виклику:</i>"
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "mkt_main_hub")
async def cb_back_to_main_hub(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await cmd_marketplace_main(callback.message, state)


# ==========================================
# 5. ОФОРМЛЕННЯ ЗАМОВЛЕННЯ ПОСЛУГИ
# ==========================================

@router.callback_query(F.data.startswith("mkt_item_direct_"))
async def cb_order_direct_item(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.replace("mkt_item_direct_", "").split("_", 1)
    cat_key = parts[0]
    s_code = parts[1]
    
    c = CONTRACTORS_CATALOG.get(cat_key)
    if not c:
        return
        
    chosen_service = None
    for code, title, price in c["services"]:
        if code == s_code or code == f"{cat_key}_{s_code}":
            chosen_service = (title, price)
            break
            
    if not chosen_service:
        chosen_service = (c["services"][0][1], c["services"][0][2])

    title, price = chosen_service
    await state.update_data(
        item_title=title,
        item_price=price,
        contractor_name=c["name"],
        contractor_company=c["company"]
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ Підтвердити та обрати час", callback_data="mkt_order_proceed")],
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="mkt_main_hub")]
        ]
    )

    text = (
        f"📋 <b>КАРТКА ЗАМОВЛЕННЯ ПОСЛУГИ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛠 <b>Послуга:</b> {title}\n"
        f"👷‍♂️ <b>Виконавець:</b> {c['name']} ({c['company']})\n"
        f"⭐️ <b>Рейтинг майстра:</b> {c['rating']} / 5.0\n"
        f"💰 <b>Орієнтовна вартість:</b> <b>від {int(price)} грн</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<i>Бажаєте викликати майстра?</i>"
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "mkt_order_proceed")
async def cb_order_proceed(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    title = data.get("item_title", "Послуга")
    
    await callback.message.delete()
    await callback.message.answer(
        f"📅 <b>Замовлення послуги: «{title}»</b>\n\n"
        f"Вкажіть <b>бажану дату та час візиту майстра</b>:\n"
        f"<i>(Наприклад: «Сьогодні після 18:00» або «Завтра з 10:00 до 13:00»)</i>",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(MarketplaceOrderState.waiting_for_time)


@router.message(MarketplaceOrderState.waiting_for_time, F.text)
async def process_order_time(message: Message, state: FSMContext):
    pref_time = message.text.strip()
    await state.update_data(preferred_time=pref_time)
    
    await message.answer(
        "📝 Додайте <b>коментар для майстра</b> (опишіть проблему детальніше або відправте «-»):",
        parse_mode="HTML"
    )
    await state.set_state(MarketplaceOrderState.waiting_for_comment)


@router.message(MarketplaceOrderState.waiting_for_comment, F.text)
async def process_order_comment(message: Message, state: FSMContext, bot: Bot):
    comment = message.text.strip()
    if comment == "-":
        comment = None

    data = await state.get_data()
    title = data.get("item_title", "Послуга майстра")
    price = data.get("item_price", 0.0)
    contractor = data.get("contractor_name", "Закріплений спеціаліст")
    pref_time = data.get("preferred_time", "У найближчий час")
    telegram_id = message.from_user.id

    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()
        if not user:
            await message.answer("⚠️ Будь ласка, зареєструйтесь через /start.")
            return

        apt_res = await session.execute(select(Apartment).where(Apartment.resident_id == user.id))
        apt = apt_res.scalar_one_or_none()
        apt_num = apt.number if apt else "—"

        order = ServiceOrder(
            user_id=user.id,
            apartment_id=apt.id if apt else None,
            service_title=f"{title} ({contractor})",
            price_est=price,
            preferred_time=pref_time,
            contact_phone=user.phone or "Вказано в профілі",
            comment=comment,
            status=ServiceOrderStatus.PENDING
        )
        session.add(order)
        await session.commit()
        order_id = order.id

    await state.clear()

    confirm_text = (
        f"🎉 <b>ЕЛЕКТРОННЕ ЗАМОВЛЕННЯ №{order_id:04d} ПРИЙНЯТО!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛠 <b>Послуга:</b> {title}\n"
        f"👷‍♂️ <b>Призначений майстер:</b> {contractor}\n"
        f"💰 <b>Орієнтовна вартість:</b> від {price:.2f} грн\n"
        f"⏰ <b>Бажаний час візиту:</b> {pref_time}\n"
        f"🏢 <b>Адреса:</b> Квартира №{apt_num}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📞 <i>Майстер зв'яжеться з вами протягом 15 хвилин для підтвердження візиту. Оплата здійснюється після виконання робіт.</i>"
    )
    await message.answer(confirm_text, reply_markup=get_main_menu_keyboard(user.role), parse_mode="HTML")


# ==========================================
# 6. МОЇ ЗАМОВЛЕННЯ
# ==========================================

@router.callback_query(F.data == "mkt_my_orders")
async def cb_my_orders(callback: CallbackQuery):
    await callback.answer()
    telegram_id = callback.from_user.id

    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()
        if not user:
            return

        orders_res = await session.execute(
            select(ServiceOrder).where(ServiceOrder.user_id == user.id).order_by(desc(ServiceOrder.id)).limit(5)
        )
        orders = orders_res.scalars().all()

    if not orders:
        text = (
            "📦 <b>Мої замовлення послуг</b>\n\n"
            "У вас поки немає активних або минулих замовлень.\n"
            "Ви можете замовити майстра в будь-який зручний момент з каталогу!"
        )
    else:
        text = "📦 <b>Ваші останні замовлення послуг:</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for o in orders:
            status_badge = {
                ServiceOrderStatus.PENDING: "Очікує підтвердження ⏳",
                ServiceOrderStatus.CONFIRMED: "Прийнято в роботу ✅",
                ServiceOrderStatus.COMPLETED: "Виконано 🎉",
                ServiceOrderStatus.CANCELLED: "Скасовано ❌"
            }.get(o.status, "В обробці")

            text += (
                f"🏷 <b>Замовлення №{o.id:04d}</b>\n"
                f"🛠 <b>Послуга:</b> {o.service_title}\n"
                f"⏰ <b>Час:</b> {o.preferred_time or 'Не вказано'}\n"
                f"📌 <b>Статус:</b> <b>{status_badge}</b>\n"
                f"💰 <b>Сума:</b> {o.price_est:.2f} грн\n\n"
            )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад до маркетплейсу", callback_data="mkt_main_hub")]]
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
