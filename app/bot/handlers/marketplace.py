from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, desc, or_
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
@router.message(F.text.contains("Маркетплейс") | F.text.contains("Послуги") | F.text.contains("майстрів") | F.text.contains("Платні") | F.text.contains("послуг"))
@router.callback_query(F.data == "mkt_main_hub")
@router.callback_query(F.data == "mkt_back_main")
@router.callback_query(F.data == "mkt_start")
@router.callback_query(F.data == "marketplace_main")
async def cmd_marketplace_main(event: Message | CallbackQuery, state: FSMContext):
    """Головне меню маркетплейсу послуг та підрядників"""
    await state.clear()
    if isinstance(event, CallbackQuery):
        await event.answer()

    message = event if isinstance(event, Message) else event.message
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🚰 Сантехнічні роботи", callback_data="mkt_cat_plumbing"),
                InlineKeyboardButton(text="💡 Електрика", callback_data="mkt_cat_electricity")
            ],
            [
                InlineKeyboardButton(text="🧹 Клінінг та чистота", callback_data="mkt_cat_cleaning"),
                InlineKeyboardButton(text="❄️ Кондиціонери", callback_data="mkt_cat_ac")
            ],
            [
                InlineKeyboardButton(text="🔑 Замки та двері", callback_data="mkt_cat_locks"),
                InlineKeyboardButton(text="🚚 Вантажники та вивіз", callback_data="mkt_cat_logistics")
            ],
            [
                InlineKeyboardButton(text="👷‍♂️ Реєстр майстрів (Анкети)", callback_data="mkt_contractors_list"),
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
    
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await event.message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
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

CAT_ALIASES = {
    "plumbing": "plumbing",
    "elec": "electricity",
    "electricity": "electricity",
    "clean": "cleaning",
    "cleaning": "cleaning",
    "ac": "ac",
    "lock": "locks",
    "locks": "locks",
    "logistics": "logistics",
    "log": "logistics"
}


async def render_category_screen(message: Message, cat_code: str):
    cat_code = CAT_ALIASES.get(cat_code, cat_code)
    c = CONTRACTORS_CATALOG.get(cat_code, CONTRACTORS_CATALOG["plumbing"])

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
        f"<i>Оберіть потрібну послугу зі списку нижче:</i>"
    )
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(F.text.contains("Сантехн"))
async def msg_cat_plumbing(message: Message, state: FSMContext):
    await state.clear()
    await render_category_screen(message, "plumbing")


@router.message(F.text.contains("Електрик"))
async def msg_cat_electricity(message: Message, state: FSMContext):
    await state.clear()
    await render_category_screen(message, "electricity")


@router.message(F.text.contains("Клінінг"))
async def msg_cat_cleaning(message: Message, state: FSMContext):
    await state.clear()
    await render_category_screen(message, "cleaning")


@router.message(F.text.contains("Кондиціонер"))
async def msg_cat_ac(message: Message, state: FSMContext):
    await state.clear()
    await render_category_screen(message, "ac")


@router.message(F.text.contains("Замки") | F.text.contains("двері"))
async def msg_cat_locks(message: Message, state: FSMContext):
    await state.clear()
    await render_category_screen(message, "locks")


@router.message(F.text.contains("Вантажн"))
async def msg_cat_logistics(message: Message, state: FSMContext):
    await state.clear()
    await render_category_screen(message, "logistics")


@router.callback_query(F.data.startswith("mkt_cat_"))
async def cb_show_category(callback: CallbackQuery):
    await callback.answer()
    raw_code = callback.data.replace("mkt_cat_", "")
    cat_code = CAT_ALIASES.get(raw_code, raw_code)
    c = CONTRACTORS_CATALOG.get(cat_code)
    
    if not c:
        cat_code = "plumbing"
        c = CONTRACTORS_CATALOG[cat_code]

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
        f"<i>Оберіть потрібну послугу зі списку нижче:</i>"
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "mkt_main_hub")
async def cb_back_to_main_hub(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await cmd_marketplace_main(callback.message, state)


# ==========================================
# 5. ОФОРМЛЕННЯ ЗАМОВЛЕННЯ ПОСЛУГИ
# ==========================================

@router.callback_query(F.data.startswith("mkt_item_"))
async def cb_order_item_generic(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw = callback.data.replace("mkt_item_direct_", "").replace("mkt_item_", "")
    
    chosen_cat = None
    chosen_service = None
    
    # Шукаємо послугу серед усіх категорій
    for cat_key, c in CONTRACTORS_CATALOG.items():
        for s_code, s_title, s_price in c["services"]:
            if raw == s_code or raw == f"{cat_key}_{s_code}" or raw.endswith(s_code) or s_code in raw:
                chosen_cat = c
                chosen_service = (s_title, s_price)
                break
        if chosen_service:
            break
            
    if not chosen_cat:
        chosen_cat = CONTRACTORS_CATALOG["plumbing"]
        chosen_service = (chosen_cat["services"][0][1], chosen_cat["services"][0][2])

    title, price = chosen_service
    await state.update_data(
        item_title=title,
        item_price=price,
        contractor_name=chosen_cat["name"],
        contractor_company=chosen_cat["company"]
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
        f"👷‍♂️ <b>Виконавець:</b> {chosen_cat['name']} ({chosen_cat['company']})\n"
        f"⭐️ <b>Рейтинг майстра:</b> {chosen_cat['rating']} / 5.0\n"
        f"💰 <b>Орієнтовна вартість:</b> <b>від {int(price)} грн</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<i>Бажаєте викликати майстра?</i>"
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "mkt_order_proceed")
async def cb_order_proceed(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    title = data.get("item_title") or "Послуга майстра"
    contractor = data.get("contractor_name") or "Закріплений спеціаліст"
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ Терміново (протягом 1-2 год)", callback_data="mkt_set_time_urgent")],
            [InlineKeyboardButton(text="🌅 Сьогодні після 18:00", callback_data="mkt_set_time_today_eve")],
            [InlineKeyboardButton(text="☀️ Завтра (10:00 - 13:00)", callback_data="mkt_set_time_tmrw_morn")],
            [InlineKeyboardButton(text="🌆 Завтра (14:00 - 18:00)", callback_data="mkt_set_time_tmrw_eve")],
            [InlineKeyboardButton(text="📅 Вихідні (Субота 11:00)", callback_data="mkt_set_time_weekend")],
            [InlineKeyboardButton(text="✍️ Вказати власний час", callback_data="mkt_custom_time_prompt")],
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="mkt_main_hub")]
        ]
    )

    text = (
        f"📅 <b>ОБЕРІТЬ ЧАС ВІЗИТУ МАЙСТРА</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛠 <b>Послуга:</b> {title}\n"
        f"👷‍♂️ <b>Виконавець:</b> {contractor}\n\n"
        f"👉 <b>Оберіть кнопку зі зручним часом</b> або натисніть <b>«✍️ Вказати власний час»</b>:"
    )
    
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")

    await state.set_state(MarketplaceOrderState.waiting_for_time)


@router.callback_query(F.data == "mkt_custom_time_prompt")
async def cb_custom_time_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    title = data.get("item_title") or "Послуга майстра"
    contractor = data.get("contractor_name") or "Закріплений спеціаліст"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 До швидких варіантів", callback_data="mkt_order_proceed")],
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="mkt_main_hub")]
        ]
    )

    text = (
        f"✍️ <b>ВВЕДЕННЯ ВЛАСНОГО ЧАСУ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛠 <b>Послуга:</b> {title}\n"
        f"👷‍♂️ <b>Майстер:</b> {contractor}\n\n"
        f"Напишіть у повідомленні <b>бажану дату та час візиту</b>:\n"
        f"<i>(Наприклад: «П'ятниця о 16:30», «25 серпня після 19:00» або «Завтра з 12 до 14»)</i>"
    )
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")

    await state.set_state(MarketplaceOrderState.waiting_for_time)


@router.callback_query(F.data.startswith("mkt_set_time_"))
async def cb_quick_time_select(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    time_map = {
        "mkt_set_time_urgent": "⚡️ Терміново (протягом 1-2 год)",
        "mkt_set_time_today_eve": "🌅 Сьогодні після 18:00",
        "mkt_set_time_tmrw_morn": "☀️ Завтра з 10:00 до 13:00",
        "mkt_set_time_tmrw_eve": "🌆 Завтра з 14:00 до 18:00",
        "mkt_set_time_weekend": "📅 На вихідних (Субота 11:00)"
    }
    chosen_time = time_map.get(callback.data, "У найближчий зручний час")
    await finalize_marketplace_order(
        event=callback,
        state=state,
        pref_time=chosen_time,
        telegram_id=callback.from_user.id
    )


@router.message(MarketplaceOrderState.waiting_for_time, F.text)
async def process_order_time(message: Message, state: FSMContext):
    pref_time = message.text.strip()
    await finalize_marketplace_order(
        event=message,
        state=state,
        pref_time=pref_time,
        telegram_id=message.from_user.id
    )


async def finalize_marketplace_order(event: Message | CallbackQuery, state: FSMContext, pref_time: str, telegram_id: int):
    data = await state.get_data()
    title = data.get("item_title") or "Послуга майстра"
    price = data.get("item_price", 450.0)
    contractor = data.get("contractor_name") or "Закріплений спеціаліст"

    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()
        if not user:
            msg = "⚠️ Будь ласка, зареєструйтесь через /start."
            if isinstance(event, CallbackQuery):
                await event.message.answer(msg)
            else:
                await event.answer(msg)
            await state.clear()
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
            status=ServiceOrderStatus.PENDING
        )
        session.add(order)
        await session.commit()
        order_id = order.id

        # Отримуємо підрядників для надсилання сповіщення
        masters_res = await session.execute(
            select(User).where(
                or_(User.role == UserRole.CONTRACTOR, User.contractor_category.isnot(None)),
                User.telegram_id != telegram_id
            )
        )
        registered_masters = masters_res.scalars().all()

    await state.clear()

    # Надсилаємо сповіщення підрядникам
    bot = event.bot if hasattr(event, "bot") else None
    if bot:
        for m in registered_masters:
            if m.telegram_id:
                try:
                    master_kb = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(text="✅ Прийняти замовлення", callback_data=f"master_accept_order_{order_id}"),
                                InlineKeyboardButton(text="❌ Відхилити", callback_data=f"master_decline_order_{order_id}")
                            ]
                        ]
                    )
                    await bot.send_message(
                        chat_id=m.telegram_id,
                        text=(
                            f"🔔 <b>НОВЕ ЗАМОВЛЕННЯ №{order_id:04d} В МАРКЕТПЛЕЙСІ!</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"🛠 <b>Послуга:</b> {title}\n"
                            f"💰 <b>Орієнтовна сума:</b> ~{price:.2f} грн\n"
                            f"⏰ <b>Бажаний час:</b> <b>{pref_time}</b>\n"
                            f"🏢 <b>Адреса:</b> Квартира №{apt_num}\n"
                            f"📱 <b>Телефон клієнта:</b> <code>{user.phone or 'Вказано в базі'}</code>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"<i>Бажаєте взяти це замовлення в роботу?</i>"
                        ),
                        reply_markup=master_kb,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    pass

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📦 Переглянути мої замовлення", callback_data="mkt_my_orders")],
            [InlineKeyboardButton(text="🔙 До маркетплейсу", callback_data="mkt_main_hub")]
        ]
    )

    confirm_text = (
        f"🎉 <b>ЕЛЕКТРОННЕ ЗАМОВЛЕННЯ №{order_id:04d} УСПІШНО ПРИЙНЯТО!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛠 <b>Послуга:</b> {title}\n"
        f"👷‍♂️ <b>Призначений майстер:</b> {contractor}\n"
        f"💰 <b>Орієнтовна вартість:</b> від {price:.2f} грн\n"
        f"⏰ <b>Бажаний час візиту:</b> <b>{pref_time}</b>\n"
        f"🏢 <b>Адреса:</b> Квартира №{apt_num}\n"
        f"📌 <b>Статус:</b> ⏳ Очікує підтвердження майстром\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📞 <i>Майстер зв'яжеться з вами за номером <code>{user.phone or 'профілю'}</code> для підтвердження візиту. Оплата здійснюється після виконання робіт.</i>"
    )

    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(confirm_text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await event.message.answer(confirm_text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.answer(confirm_text, reply_markup=kb, parse_mode="HTML")


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
