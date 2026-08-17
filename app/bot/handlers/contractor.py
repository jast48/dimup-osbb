import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, desc, or_
from app.db.session import async_session_maker
from app.db.models import User, Apartment, ServiceOrder, ServiceOrderStatus, UserRole
from app.bot.states.user_states import ContractorRegistrationState
from app.bot.keyboards.keyboards import get_main_menu_keyboard, get_cancel_keyboard, get_phone_request_keyboard

logger = logging.getLogger(__name__)
router = Router()

CATEGORIES_DICT = {
    "plumbing": "🚰 Сантехніка",
    "electricity": "💡 Електрика",
    "cleaning": "🧹 Клінінг",
    "ac": "❄️ Кондиціонери",
    "locks": "🔑 Замки та двері",
    "logistics": "🚚 Вантажники / Перевезення",
    "other": "🛠 Інші побутові послуги"
}


# ==========================================
# 1. ОНБОРДИНГ ТА РЕЄСТРАЦІЯ ПІДРЯДНИКА
# ==========================================

@router.callback_query(F.data == "start_register_contractor")
@router.message(Command("become_master"))
async def start_contractor_registration(event: Message | CallbackQuery, state: FSMContext):
    """Початок реєстрації нового підрядника / майстра"""
    await state.clear()
    if isinstance(event, CallbackQuery):
        await event.answer()

    message = event if isinstance(event, Message) else event.message

    buttons = []
    for code, title in CATEGORIES_DICT.items():
        buttons.append([InlineKeyboardButton(text=title, callback_data=f"reg_master_cat_{code}")])
    buttons.append([InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel_contractor_reg")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = (
        "🛠 <b>РЕЄСТРАЦІЯ ПІДРЯДНИКА / МАЙСТРА В DIMUP</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Приєднуйтесь до офіційного маркетплейсу будинку та отримуйте замовлення від мешканців напряму без посередників!\n\n"
        "📌 <b>Оберіть вашу основну спеціалізацію:</b>"
    )
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

    await state.set_state(ContractorRegistrationState.waiting_for_category)


@router.callback_query(F.data == "cancel_contractor_reg")
async def cb_cancel_contractor_reg(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    telegram_id = callback.from_user.id
    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()
        role = user.role if user else UserRole.RESIDENT
    await callback.message.delete()
    await callback.message.answer("Реєстрацію майстра скасовано.", reply_markup=get_main_menu_keyboard(role))


@router.callback_query(ContractorRegistrationState.waiting_for_category, F.data.startswith("reg_master_cat_"))
async def process_contractor_category(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    cat_code = callback.data.replace("reg_master_cat_", "")
    cat_name = CATEGORIES_DICT.get(cat_code, "🛠 Загальні послуги")
    await state.update_data(contractor_category=cat_name, contractor_cat_code=cat_code)

    await callback.message.delete()
    await callback.message.answer(
        f"✅ Спеціалізація: <b>{cat_name}</b>\n\n"
        f"👤 Введіть ваше <b>Прізвище, Ім'я або назву ФОП / компанії</b>:\n"
        f"<i>(Наприклад: «Олексій Коваленко» або «ФОП Мельник / Сантехсервіс»)</i>",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(ContractorRegistrationState.waiting_for_full_name)


@router.message(ContractorRegistrationState.waiting_for_full_name, F.text)
async def process_contractor_name(message: Message, state: FSMContext):
    full_name = message.text.strip()
    if len(full_name) < 3:
        await message.answer("⚠️ Будь ласка, введіть коректне ім'я або назву компанії:")
        return

    await state.update_data(full_name=full_name)
    await message.answer(
        f"📝 Вкажіть ваш <b>досвід роботи або короткий опис послуг</b> (або відправте «-»):\n"
        f"<i>(Наприклад: «7 років досвіду, гарантія на всі сантехнічні роботи 1 рік»)</i>",
        parse_mode="HTML"
    )
    await state.set_state(ContractorRegistrationState.waiting_for_company)


@router.message(ContractorRegistrationState.waiting_for_company, F.text)
async def process_contractor_company(message: Message, state: FSMContext):
    company_info = message.text.strip()
    if company_info == "-":
        company_info = "Акредитований спеціаліст"

    await state.update_data(contractor_company=company_info)
    await message.answer(
        "📱 <b>Останній крок:</b> вкажіть ваш <b>контактний номер телефону</b>, за яким мешканці та диспетчер зможуть зв'язуватися щодо замовлень:\n\n"
        "Натисніть кнопку <b>«📱 Поділитися контактом»</b> або введіть номер вручну:",
        reply_markup=get_phone_request_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(ContractorRegistrationState.waiting_for_phone)


@router.message(ContractorRegistrationState.waiting_for_phone, F.contact | F.text)
async def process_contractor_phone(message: Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text.strip()
    data = await state.get_data()
    
    full_name = data.get("full_name", "Майстер")
    category = data.get("contractor_category", "🛠 Послуги")
    company = data.get("contractor_company", "Акредитований майстер")
    telegram_id = message.from_user.id
    username = message.from_user.username

    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()

        if user:
            user.role = UserRole.CONTRACTOR
            user.contractor_category = category
            user.contractor_company = company
            user.phone = phone
            user.is_verified = True
        else:
            user = User(
                telegram_id=telegram_id,
                username=username,
                full_name=full_name,
                phone=phone,
                role=UserRole.CONTRACTOR,
                contractor_category=category,
                contractor_company=company,
                contractor_rating=5.0,
                contractor_orders_count=0,
                is_verified=True
            )
            session.add(user)

        await session.commit()

    await state.clear()

    confirm_text = (
        f"🎉 <b>ВІТАЄМО, ВИ УСПІШНО ЗАРЕЄСТРОВАНІ ЯК ПІДРЯДНИК!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Спеціаліст:</b> {full_name}\n"
        f"📌 <b>Спеціалізація:</b> {category}\n"
        f"🏢 <b>Опис:</b> {company}\n"
        f"📱 <b>Телефон:</b> {phone}\n"
        f"⭐️ <b>Початковий рейтинг:</b> 5.0 / 5.0\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔔 <i>Тепер ви будете автоматично отримувати сповіщення про нові замовлення від мешканців будинку у цьому боті!</i>"
    )
    await message.answer(confirm_text, reply_markup=get_main_menu_keyboard(UserRole.CONTRACTOR), parse_mode="HTML")


# ==========================================
# 2. ПАНЕЛЬ ТА МЕНЮ ПІДРЯДНИКА
# ==========================================

@router.message(F.text == "📥 Нові замовлення")
async def cmd_contractor_new_orders(message: Message):
    """Список новых заказов, ожидающих подтверждения"""
    telegram_id = message.from_user.id
    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()
        if not user or user.role != UserRole.CONTRACTOR:
            await message.answer("⚠️ Цей розділ доступний лише зареєстрованим підрядникам.")
            return

        orders_res = await session.execute(
            select(ServiceOrder).where(ServiceOrder.status == ServiceOrderStatus.PENDING).order_by(desc(ServiceOrder.id)).limit(10)
        )
        orders = orders_res.scalars().all()

        orders_data = []
        for o in orders:
            client_res = await session.execute(select(User).where(User.id == o.user_id))
            client = client_res.scalar_one_or_none()
            apt_res = await session.execute(select(Apartment).where(Apartment.id == o.apartment_id))
            apt = apt_res.scalar_one_or_none()
            orders_data.append((o, client, apt))

    if not orders_data:
        await message.answer(
            "📥 <b>Нові замовлення:</b>\n\n"
            "Наразі немає відкритих замовлень. Як тільки мешканець створить заявку на виклик майстра, ви отримаєте миттєве сповіщення!",
            parse_mode="HTML"
        )
        return

    await message.answer(f"📥 <b>Доступні нові замовлення ({len(orders_data)}):</b>\n━━━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML")

    for o, client, apt in orders_data:
        client_name = client.full_name if client else "Мешканець"
        client_apt = f"№{apt.number}" if apt else "—"
        client_phone = client.phone if client and client.phone else (o.contact_phone or "—")

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Прийняти замовлення", callback_data=f"master_accept_order_{o.id}"),
                    InlineKeyboardButton(text="❌ Відхилити", callback_data=f"master_decline_order_{o.id}")
                ]
            ]
        )
        card_text = (
            f"🏷 <b>Замовлення №{o.id:04d}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛠 <b>Послуга:</b> {o.service_title}\n"
            f"💰 <b>Бюджет:</b> ~{o.price_est:.2f} грн\n"
            f"⏰ <b>Бажаний час:</b> <b>{o.preferred_time or 'Якнайшвидше'}</b>\n"
            f"🏢 <b>Квартира:</b> {client_apt}\n"
            f"👤 <b>Замовник:</b> {client_name}\n"
            f"📱 <b>Телефон:</b> <code>{client_phone}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        )
        await message.answer(card_text, reply_markup=kb, parse_mode="HTML")


@router.message(F.text == "📋 Мої активні роботи")
async def cmd_contractor_active_orders(message: Message):
    """Список активних замовлень у роботі з повною карткою клієнта"""
    telegram_id = message.from_user.id
    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()
        if not user or user.role != UserRole.CONTRACTOR:
            return

        orders_res = await session.execute(
            select(ServiceOrder).where(
                ServiceOrder.assigned_contractor_id == user.id,
                ServiceOrder.status == ServiceOrderStatus.CONFIRMED
            ).order_by(desc(ServiceOrder.id))
        )
        orders = orders_res.scalars().all()

        # Збираємо дані клієнтів
        orders_data = []
        for o in orders:
            client_res = await session.execute(select(User).where(User.id == o.user_id))
            client = client_res.scalar_one_or_none()
            apt_res = await session.execute(select(Apartment).where(Apartment.id == o.apartment_id))
            apt = apt_res.scalar_one_or_none()
            orders_data.append((o, client, apt))

    if not orders_data:
        await message.answer(
            "📋 <b>Активні роботи:</b>\n\n"
            "У вас немає замовлень у процесі виконання.\n"
            "Перегляньте нові замовлення за кнопкою <b>«📥 Нові замовлення»</b>!",
            parse_mode="HTML"
        )
        return

    for o, client, apt in orders_data:
        client_name = client.full_name if client else "Мешканець"
        client_phone = client.phone if client and client.phone else (o.contact_phone or "Не вказано")
        client_apt = f"№{apt.number}" if apt else "Не вказано"
        client_tg = f"@{client.username}" if client and client.username else "—"

        buttons = []
        if client and client.username:
            buttons.append([InlineKeyboardButton(text="💬 Написати клієнту в Telegram", url=f"https://t.me/{client.username}")])
        elif client and client.telegram_id:
            buttons.append([InlineKeyboardButton(text="💬 Написати клієнту", url=f"tg://user?id={client.telegram_id}")])

        buttons.append([InlineKeyboardButton(text="🏁 Роботу виконано", callback_data=f"master_complete_order_{o.id}")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

        card_text = (
            f"🛠 <b>Замовлення №{o.id:04d} [В РОБОТІ]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Послуга:</b> {o.service_title}\n"
            f"💰 <b>Сума до розрахунку:</b> {o.price_est:.2f} грн\n"
            f"⏰ <b>Час візиту:</b> <b>{o.preferred_time or 'Якнайшвидше'}</b>\n\n"
            f"👤 <b>КАРТКА КЛІЄНТА / ОБ'ЄКТА:</b>\n"
            f"• <b>Ім'я замовника:</b> {client_name}\n"
            f"• <b>Квартира:</b> {client_apt}\n"
            f"• <b>Телефон:</b> <code>{client_phone}</code>\n"
            f"• <b>Telegram:</b> {client_tg}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        )
        await message.answer(card_text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("master_accept_order_"))
async def cb_master_accept_order(callback: CallbackQuery, bot: Bot):
    order_id = int(callback.data.split("_")[3])
    telegram_id = callback.from_user.id

    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        master = user_res.scalar_one_or_none()

        order_res = await session.execute(select(ServiceOrder).where(ServiceOrder.id == order_id))
        order = order_res.scalar_one_or_none()

        if not order:
            await callback.answer("Замовлення не знайдено.")
            return

        if order.status != ServiceOrderStatus.PENDING:
            await callback.answer("⚠️ Це замовлення вже прийнято іншим майстром!", show_alert=True)
            await callback.message.delete()
            return

        order.status = ServiceOrderStatus.CONFIRMED
        order.assigned_contractor_id = master.id
        await session.commit()

        # Отримуємо замовника та квартиру для повної картки
        client_res = await session.execute(select(User).where(User.id == order.user_id))
        client = client_res.scalar_one_or_none()

        apt_res = await session.execute(select(Apartment).where(Apartment.id == order.apartment_id))
        apt = apt_res.scalar_one_or_none()

    client_name = client.full_name if client else "Мешканець"
    client_phone = client.phone if client and client.phone else (order.contact_phone or "Не вказано")
    client_apt = f"№{apt.number}" if apt else "Не вказано"
    client_tg = f"@{client.username}" if client and client.username else "—"

    buttons = []
    if client and client.username:
        buttons.append([InlineKeyboardButton(text="💬 Написати клієнту в Telegram", url=f"https://t.me/{client.username}")])
    elif client and client.telegram_id:
        buttons.append([InlineKeyboardButton(text="💬 Написати клієнту", url=f"tg://user?id={client.telegram_id}")])

    buttons.append([InlineKeyboardButton(text="🏁 Роботу виконано", callback_data=f"master_complete_order_{order_id}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    card_text = (
        f"✅ <b>Замовлення №{order_id:04d} ПРИЙНЯТО В РОБОТУ!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛠 <b>Послуга:</b> {order.service_title}\n"
        f"💰 <b>Бюджет:</b> {order.price_est:.2f} грн\n"
        f"⏰ <b>Час візиту:</b> <b>{order.preferred_time or 'Якнайшвидше'}</b>\n\n"
        f"👤 <b>КАРТКА ЗАМОВНИКА / АДРЕСА:</b>\n"
        f"• <b>Клієнт:</b> {client_name}\n"
        f"• <b>Квартира:</b> {client_apt}\n"
        f"• <b>Телефон:</b> <code>{client_phone}</code>\n"
        f"• <b>Telegram:</b> {client_tg}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<i>Зв'яжіться з клієнтом за потреби. Після виконання замовлення натисніть кнопку «🏁 Роботу виконано».</i>"
    )

    await callback.answer("✅ Ви успішно прийняли замовлення в роботу!", show_alert=True)
    await callback.message.edit_text(card_text, reply_markup=kb, parse_mode="HTML")

    # Сповіщаємо мешканця
    if client and client.telegram_id:
        try:
            await bot.send_message(
                chat_id=client.telegram_id,
                text=(
                    f"🎉 <b>ВАШЕ ЗАМОВЛЕННЯ №{order_id:04d} ПРИЙНЯТО!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👷‍♂️ <b>Призначений майстер:</b> {master.full_name}\n"
                    f"📱 <b>Телефон майстра:</b> <code>{master.phone or 'Вказано в базі'}</code>\n"
                    f"⏰ <b>Погоджений час візиту:</b> <b>{order.preferred_time}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"<i>Майстер прибуде у вказаний час. Оплата здійснюється після завершення та перевірки якості робіт.</i>"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.debug("Failed to notify resident: %s", e)


@router.callback_query(F.data.startswith("master_complete_order_"))
async def cb_master_complete_order(callback: CallbackQuery, bot: Bot):
    order_id = int(callback.data.split("_")[3])
    telegram_id = callback.from_user.id

    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        master = user_res.scalar_one_or_none()

        order_res = await session.execute(select(ServiceOrder).where(ServiceOrder.id == order_id))
        order = order_res.scalar_one_or_none()

        if order and order.assigned_contractor_id == master.id:
            order.status = ServiceOrderStatus.COMPLETED
            if master.contractor_orders_count is not None:
                master.contractor_orders_count += 1
            else:
                master.contractor_orders_count = 1
            await session.commit()

            client_res = await session.execute(select(User).where(User.id == order.user_id))
            client = client_res.scalar_one_or_none()
        else:
            await callback.answer("Замовлення не знайдено.")
            return

    await callback.answer("🎉 Замовлення позначено як виконане!")
    await callback.message.edit_text(
        f"🎉 <b>Замовлення №{order_id:04d} успішно завершено!</b>\n\n"
        f"Дякуємо за якісну роботу на користь нашого будинку!",
        parse_mode="HTML"
    )

    # Запит відгуку у мешканця
    if client and client.telegram_id:
        try:
            rating_kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="⭐️ 1", callback_data=f"rate_order_{order_id}_1"),
                        InlineKeyboardButton(text="⭐️ 2", callback_data=f"rate_order_{order_id}_2"),
                        InlineKeyboardButton(text="⭐️ 3", callback_data=f"rate_order_{order_id}_3"),
                        InlineKeyboardButton(text="⭐️ 4", callback_data=f"rate_order_{order_id}_4"),
                        InlineKeyboardButton(text="⭐️ 5", callback_data=f"rate_order_{order_id}_5")
                    ]
                ]
            )
            await bot.send_message(
                chat_id=client.telegram_id,
                text=(
                    f"🏁 <b>Роботу по замовленню №{order_id:04d} завершено!</b>\n\n"
                    f"🛠 <b>Послуга:</b> {order.service_title}\n"
                    f"👷‍♂️ <b>Майстер:</b> {master.full_name}\n\n"
                    f"Будь ласка, <b>оцініть якість виконання робіт</b>:"
                ),
                reply_markup=rating_kb,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.debug("Failed to send review prompt: %s", e)


@router.callback_query(F.data.startswith("rate_order_"))
async def cb_rate_order(callback: CallbackQuery):
    parts = callback.data.split("_")
    order_id = int(parts[2])
    score = int(parts[3])

    async with async_session_maker() as session:
        order_res = await session.execute(select(ServiceOrder).where(ServiceOrder.id == order_id))
        order = order_res.scalar_one_or_none()
        if order:
            order.rating = score
            if order.assigned_contractor_id:
                master_res = await session.execute(select(User).where(User.id == order.assigned_contractor_id))
                master = master_res.scalar_one_or_none()
                if master:
                    curr_rating = master.contractor_rating or 5.0
                    master.contractor_rating = round((curr_rating * 0.8) + (score * 0.2), 2)
            await session.commit()

    await callback.answer(f"Дякуємо за оцінку {score}⭐️!", show_alert=True)
    await callback.message.edit_text(
        f"⭐️ <b>Дякуємо за ваш відгук ({score}/5)!</b>\nВаша оцінка допомагає підтримувати високу якість послуг у будинку.",
        parse_mode="HTML"
    )


@router.message(F.text == "⭐️ Рейтинг та відгуки")
async def cmd_contractor_rating(message: Message):
    telegram_id = message.from_user.id
    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()
        if not user or user.role != UserRole.CONTRACTOR:
            return

    rating_text = (
        f"⭐️ <b>ВАШ РЕЙТИНГ ТА СТАТИСТИКА</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Спеціаліст:</b> {user.full_name}\n"
        f"📌 <b>Спеціалізація:</b> {user.contractor_category or 'Майстер'}\n"
        f"⭐️ <b>Поточний рейтинг:</b> <b>{user.contractor_rating or 5.0:.2f} / 5.0</b>\n"
        f"📦 <b>Виконано замовлень:</b> <b>{user.contractor_orders_count or 0}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<i>Рейтинг розраховується автоматично на основі оцінок мешканців після завершення робіт.</i>"
    )
    await message.answer(rating_text, parse_mode="HTML")


@router.message(F.text == "⚙️ Профіль майстра")
async def cmd_contractor_profile(message: Message):
    telegram_id = message.from_user.id
    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()
        if not user or user.role != UserRole.CONTRACTOR:
            return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Змінити спеціалізацію", callback_data="start_register_contractor")],
            [InlineKeyboardButton(text="🏠 Перемкнути на режим мешканця", callback_data="switch_to_resident")]
        ]
    )
    text = (
        f"⚙️ <b>ПРОФІЛЬ ПІДРЯДНИКА</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>ПІБ / Назва:</b> {user.full_name}\n"
        f"📌 <b>Категорія:</b> {user.contractor_category}\n"
        f"🏢 <b>Компанія / Опис:</b> {user.contractor_company}\n"
        f"📱 <b>Телефон:</b> {user.phone}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "switch_to_resident")
@router.message(F.text == "🏠 Режим мешканця")
async def cb_switch_to_resident(event: Message | CallbackQuery):
    if isinstance(event, CallbackQuery):
        await event.answer()
    message = event if isinstance(event, Message) else event.message
    telegram_id = event.from_user.id

    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()
        if user:
            user.role = UserRole.RESIDENT
            await session.commit()

    text = "🏠 <b>Ви перемкнулися в режим мешканця будинку.</b>\nВам доступні всі функції жителя: квитанції, заявки, консьєрж та маркетплейс."
    await message.answer(text, reply_markup=get_main_menu_keyboard(UserRole.RESIDENT), parse_mode="HTML")


@router.callback_query(F.data == "switch_to_contractor")
async def cb_switch_to_contractor(callback: CallbackQuery):
    await callback.answer()
    telegram_id = callback.from_user.id

    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()
        if user:
            user.role = UserRole.CONTRACTOR
            await session.commit()

    await callback.message.answer(
        "🛠 <b>Ви перемкнулися в панель підрядника!</b>\nТут ви можете приймати замовлення та керувати роботами.",
        reply_markup=get_main_menu_keyboard(UserRole.CONTRACTOR),
        parse_mode="HTML"
    )
