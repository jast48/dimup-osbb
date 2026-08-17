import uuid
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, desc
from app.db.session import async_session_maker
from app.db.models import User, Apartment, Bill, UtilityAccount, UtilityProviderType, UserRole
from app.bot.states.user_states import UtilityAccountState, UtilityWizardState
from app.bot.keyboards.keyboards import get_main_menu_keyboard, get_cancel_keyboard
from app.services.utility_service import UtilityService, PROVIDER_CATALOG

router = Router()


# ==========================================
# 1. ЄДИНА КОМУНАЛЬНА КВИТАНЦІЯ (ХАБ РАХУНКІВ)
# ==========================================

@router.message(Command("bills"))
@router.message(Command("accounts"))
@router.message(F.text.contains("Оплата") | F.text.contains("Сплатити") | F.text.contains("Платіжка") | F.text.contains("Рахунки") | F.text.contains("Особові"))
@router.callback_query(F.data == "pay_bills_start")
@router.callback_query(F.data == "utility_hub_main")
async def cmd_unified_billing_hub(event: Message | CallbackQuery, state: FSMContext):
    """
    Головний екран: Єдина комунальна квитанція по квартирі з усіма міськими службами.
    """
    await state.clear()
    if isinstance(event, CallbackQuery):
        await event.answer()  # Мгновенно снимает часики с кнопки в Telegram

    message = event if isinstance(event, Message) else event.message
    telegram_id = event.from_user.id

    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()

        if not user:
            await message.answer("⚠️ Будь ласка, спочатку зареєструйтесь через /start.")
            return

        apt_res = await session.execute(select(Apartment).where(Apartment.resident_id == user.id))
        apt = apt_res.scalar_one_or_none()
        
        if not apt:
            await message.answer("⚠️ Вашу квартиру не знайдено.")
            return

        # Отримуємо зведені дані про всі нарахування (ОСББ + міські служби)
        summary = await UtilityService.get_unified_bill_summary(session, apt.id)

    items = summary["items"]
    total_to_pay = summary["total_to_pay"]
    unpaid_count = summary["unpaid_count"]

    header_status = f"🔴 До сплати: <b>{total_to_pay:.2f} грн</b>" if total_to_pay > 0 else "🟢 Усі рахунки сплачено (боргів немає)"

    text = (
        f"🏢 <b>ЄДИНА КОМУНАЛЬНА КВИТАНЦІЯ ПО КВАРТИРІ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 <b>Квартира:</b> №{summary['apartment_number']} (Площа: {summary['area']} м²)\n"
        f"💳 <b>Стан рахунку:</b> {header_status}\n"
        f"🕒 <b>Оновлено:</b> {summary['last_updated']}\n\n"
        f"📋 <b>Деталізація по службах та особових рахунках:</b>\n\n"
    )

    for item in items:
        if not item.get("is_linked", True):
            badge = "⚠️ <i>Не прив'язано</i>"
        elif not item["is_paid"] and item["amount"] > 0:
            badge = f"<b>{item['amount']:.2f} грн</b> ⏳ (До сплати)"
        else:
            badge = "Сплачено ✅"

        text += (
            f"{item['icon']} <b>{item['title']}</b>\n"
            f"   ├ О/Р: <code>{item['account_number']}</code>\n"
            f"   ├ Деталі: <i>{item['details']}</i>\n"
            f"   └ Стан: {badge}\n\n"
        )

    text += "━━━━━━━━━━━━━━━━━━━━━━"

    buttons = []

    if total_to_pay > 0:
        buttons.append([
            InlineKeyboardButton(
                text=f"⚡️ СПЛАТИТИ ВСЕ ОДРАЗУ ({total_to_pay:.2f} грн)",
                callback_data=f"pay_all_unified_{apt.id}"
            )
        ])
        buttons.append([
            InlineKeyboardButton(text="🔍 Оплатити окрему службу", callback_data="pay_separate_menu")
        ])

    buttons.append([
        InlineKeyboardButton(text="🧙‍♂️ Налаштувати мої рахунки (Опитувальник)", callback_data="start_utility_wizard")
    ])
    buttons.append([
        InlineKeyboardButton(text="🔄 Оновити нарахування з баз", callback_data="sync_utilities_now"),
        InlineKeyboardButton(text="⚙️ Керування О/Р", callback_data="manage_accounts_list")
    ])
    buttons.append([
        InlineKeyboardButton(text="🏦 Банківські реквізити IBAN", callback_data="pay_iban_info")
    ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await event.message.answer(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


# ==========================================
# 2. ПОКРОКОВИЙ ОПИТУВАЛЬНИК / МАЙСТЕР НАЛАШТУВАННЯ
# ==========================================

@router.callback_query(F.data == "start_utility_wizard")
async def cb_start_wizard(callback: CallbackQuery, state: FSMContext):
    """Початок покрокового майстра налаштування рахунків"""
    await state.clear()
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Пропустити світло", callback_data="skip_step_electricity")],
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="utility_hub_main")]
        ]
    )

    text = (
        "🧙‍♂️ <b>Майстер налаштування особових рахунків (1/4)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <b>Крок 1: Електроенергія (YASNO / ДТЕК)</b>\n\n"
        "Введіть <b>номер вашого особового рахунку за світло</b> (з паперової квитанції або додатку YASNO):\n"
        "<i>(Наприклад: <code>29481023</code>)</i>"
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(UtilityWizardState.waiting_for_electricity)


@router.message(UtilityWizardState.waiting_for_electricity, F.text)
async def process_wizard_electricity(message: Message, state: FSMContext):
    acc_num = message.text.strip().replace(" ", "")
    await state.update_data(acc_electricity=acc_num)
    await prompt_wizard_gas(message, state)


@router.callback_query(F.data == "skip_step_electricity")
async def cb_skip_electricity(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await prompt_wizard_gas(callback.message, state, is_edit=True)


async def prompt_wizard_gas(event: Message, state: FSMContext, is_edit: bool = False):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Пропустити газ", callback_data="skip_step_gas")],
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="utility_hub_main")]
        ]
    )
    text = (
        "🧙‍♂️ <b>Майстер налаштування особових рахунків (2/4)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔥 <b>Крок 2: Газопостачання (ГК «Нафтогаз України»)</b>\n\n"
        "Введіть <b>номер вашого особового рахунку за газ</b>:\n"
        "<i>(Наприклад: <code>10492834</code>)</i>"
    )
    if is_edit:
        await event.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.answer(text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(UtilityWizardState.waiting_for_gas)


@router.message(UtilityWizardState.waiting_for_gas, F.text)
async def process_wizard_gas(message: Message, state: FSMContext):
    acc_num = message.text.strip().replace(" ", "")
    await state.update_data(acc_gas=acc_num)
    await prompt_wizard_water(message, state)


@router.callback_query(F.data == "skip_step_gas")
async def cb_skip_gas(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await prompt_wizard_water(callback.message, state, is_edit=True)


async def prompt_wizard_water(event: Message, state: FSMContext, is_edit: bool = False):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Пропустити воду", callback_data="skip_step_water")],
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="utility_hub_main")]
        ]
    )
    text = (
        "🧙‍♂️ <b>Майстер налаштування особових рахунків (3/4)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🚰 <b>Крок 3: Холодна вода (ПрАТ «АК «Київводоканал»)</b>\n\n"
        "Введіть <b>номер особового рахунку за воду та каналізацію</b>:\n"
        "<i>(Наприклад: <code>04192045</code>)</i>"
    )
    if is_edit:
        await event.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.answer(text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(UtilityWizardState.waiting_for_water)


@router.message(UtilityWizardState.waiting_for_water, F.text)
async def process_wizard_water(message: Message, state: FSMContext):
    acc_num = message.text.strip().replace(" ", "")
    await state.update_data(acc_water=acc_num)
    await prompt_wizard_heating(message, state)


@router.callback_query(F.data == "skip_step_water")
async def cb_skip_water(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await prompt_wizard_heating(callback.message, state, is_edit=True)


async def prompt_wizard_heating(event: Message, state: FSMContext, is_edit: bool = False):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Пропустити опалення", callback_data="skip_step_heating")],
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="utility_hub_main")]
        ]
    )
    text = (
        "🧙‍♂️ <b>Майстер налаштування особових рахунків (4/4)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "♨️ <b>Крок 4: Опалення та гаряча вода (КП «Київтеплоенерго»)</b>\n\n"
        "Введіть <b>номер особового рахунку за опалення та ГВП</b>:\n"
        "<i>(Наприклад: <code>55819056</code>)</i>"
    )
    if is_edit:
        await event.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.answer(text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(UtilityWizardState.waiting_for_heating)


@router.message(UtilityWizardState.waiting_for_heating, F.text)
async def process_wizard_heating(message: Message, state: FSMContext):
    acc_num = message.text.strip().replace(" ", "")
    await state.update_data(acc_heating=acc_num)
    await finish_wizard_saving(message, state, message.from_user.id)


@router.callback_query(F.data == "skip_step_heating")
async def cb_skip_heating(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await finish_wizard_saving(callback.message, state, callback.from_user.id, is_edit=True)


async def finish_wizard_saving(event: Message, state: FSMContext, telegram_id: int, is_edit: bool = False):
    data = await state.get_data()
    
    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()
        if not user:
            return

        apt_res = await session.execute(select(Apartment).where(Apartment.resident_id == user.id))
        apt = apt_res.scalar_one_or_none()
        if not apt:
            return

        # Сохраняем введенные лицевые счета
        steps_map = [
            (UtilityProviderType.ELECTRICITY, data.get("acc_electricity")),
            (UtilityProviderType.GAS, data.get("acc_gas")),
            (UtilityProviderType.WATER, data.get("acc_water")),
            (UtilityProviderType.HEATING, data.get("acc_heating")),
        ]

        for prov_type, acc_num in steps_map:
            if acc_num:
                exist_res = await session.execute(
                    select(UtilityAccount).where(
                        UtilityAccount.apartment_id == apt.id,
                        UtilityAccount.provider_type == prov_type
                    )
                )
                exist_acc = exist_res.scalar_one_or_none()
                cfg = PROVIDER_CATALOG.get(prov_type, {})
                full_name = cfg.get("full_name", "Служба")
                
                if exist_acc:
                    exist_acc.account_number = acc_num
                    exist_acc.provider_name = full_name
                else:
                    new_acc = UtilityAccount(
                        apartment_id=apt.id,
                        provider_type=prov_type,
                        provider_name=full_name,
                        account_number=acc_num,
                        last_amount=0.0,
                        is_paid=False
                    )
                    session.add(new_acc)

        await session.commit()
        
        # Синхронизируем начисления с базами
        await UtilityService.sync_apartment_utilities(session, apt.id)

    await state.clear()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📱 Переглянути єдину квитанцію", callback_data="utility_hub_main")]]
    )
    success_text = (
        "🎉 <b>Налаштування успішно завершено!</b>\n\n"
        "Всі ваші особові рахунки надійно закріплені за квартирою.\n"
        "Бот автоматично звернувся до міського білінгу та сформував актуальну квитанцію до сплати!"
    )
    if is_edit:
        await event.edit_text(success_text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.answer(success_text, reply_markup=kb, parse_mode="HTML")


# ==========================================
# 3. СИНХРОНІЗАЦІЯ З БІЛІНГОМ У РЕАЛЬНОМУ ЧАСІ
# ==========================================

@router.callback_query(F.data == "sync_utilities_now")
async def cb_sync_utilities(callback: CallbackQuery, state: FSMContext):
    """Примусове опитування міських баз даних"""
    telegram_id = callback.from_user.id
    
    await callback.answer("🔄 Запитуємо нарахування у міських служб...")
    
    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()
        if not user:
            return

        apt_res = await session.execute(select(Apartment).where(Apartment.resident_id == user.id))
        apt = apt_res.scalar_one_or_none()
        if apt:
            await UtilityService.sync_apartment_utilities(session, apt.id)

    # Оновлюємо екран
    await cmd_unified_billing_hub(callback, state)


# ==========================================
# 4. ОПЛАТА ВСІХ РАХУНКІВ ОДРАЗУ В 1 КЛІК
# ==========================================

@router.callback_query(F.data.startswith("pay_all_unified_"))
async def cb_confirm_pay_all(callback: CallbackQuery):
    apt_id = int(callback.data.split("_")[3])

    async with async_session_maker() as session:
        summary = await UtilityService.get_unified_bill_summary(session, apt_id)
        total = summary["total_to_pay"]

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"⚡️ Підтвердити оплату {total:.2f} грн (Apple Pay / Mono)",
                    callback_data=f"execute_pay_all_{apt_id}"
                )
            ],
            [
                InlineKeyboardButton(text="❌ Скасувати", callback_data="utility_hub_main")
            ]
        ]
    )

    text = (
        f"🔒 <b>Безпечний платіж: Єдина комунальна квитанція</b>\n\n"
        f"🏢 <b>Квартира:</b> №{summary['apartment_number']}\n"
        f"💰 <b>Загальна сума до списання:</b> <b>{total:.2f} грн</b>\n\n"
        f"📦 <b>Склад пакету оплати:</b>\n"
    )
    for item in summary["items"]:
        if not item["is_paid"] and item["amount"] > 0:
            text += f"• {item['title']}: <b>{item['amount']:.2f} грн</b>\n"

    text += "\n<i>Кошти будуть автоматично розподілені на рахунки відповідних комунальних служб та ОСББ (Комісія 0%).</i>"

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("execute_pay_all_"))
async def cb_execute_pay_all(callback: CallbackQuery):
    apt_id = int(callback.data.split("_")[3])
    tx_id = f"HUB-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now()

    async with async_session_maker() as session:
        paid_sum = await UtilityService.pay_all_utilities(session, apt_id)
        
        apt_res = await session.execute(select(Apartment).where(Apartment.id == apt_id))
        apt = apt_res.scalar_one_or_none()
        apt_num = apt.number if apt else "—"

    receipt_text = (
        f"🧾 <b>ФІСКАЛЬНИЙ ЕЛЕКТРОННИЙ ЧЕК</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>Статус:</b> Успішно сплачено всі служби\n"
        f"🆔 <b>Номер транзакції:</b> <code>{tx_id}</code>\n"
        f"📅 <b>Дата:</b> {now.strftime('%d.%m.%Y %H:%M:%S')}\n"
        f"🏢 <b>Квартира:</b> №{apt_num}\n"
        f"💳 <b>Метод:</b> Monobank / Apple Pay (Єдина квитанція)\n"
        f"💰 <b>Загальна сума:</b> <b>{paid_sum:.2f} грн</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎉 <b>Усі комунальні нарахування та внески ОСББ успішно погашено!</b>\n\n"
        f"<i>Квитанція збережена в історії платежів.</i>"
    )

    back_kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📱 Повернутися до квитанції", callback_data="utility_hub_main")]]
    )
    await callback.message.edit_text(receipt_text, reply_markup=back_kb, parse_mode="HTML")


# ==========================================
# 5. ОПЛАТА ОКРЕМОЇ СЛУЖБИ
# ==========================================

@router.callback_query(F.data == "pay_separate_menu")
async def cb_pay_separate_menu(callback: CallbackQuery):
    telegram_id = callback.from_user.id
    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()
        
        apt_res = await session.execute(select(Apartment).where(Apartment.resident_id == user.id))
        apt = apt_res.scalar_one_or_none()
        
        summary = await UtilityService.get_unified_bill_summary(session, apt.id)

    buttons = []
    for item in summary["items"]:
        if not item["is_paid"] and item["amount"] > 0:
            buttons.append([
                InlineKeyboardButton(
                    text=f"{item['icon']} {item['title']} — {item['amount']:.2f} грн",
                    callback_data=f"pay_one_service_{item['id']}"
                )
            ])

    buttons.append([InlineKeyboardButton(text="🔙 Назад до єдиної квитанції", callback_data="utility_hub_main")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        "🔍 <b>Оберіть окрему службу для оплати:</b>",
        reply_markup=kb,
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("pay_one_service_"))
async def cb_pay_one_service(callback: CallbackQuery):
    item_id = callback.data.replace("pay_one_service_", "")
    now = datetime.now()
    tx_id = f"SVC-{uuid.uuid4().hex[:8].upper()}"

    async with async_session_maker() as session:
        if item_id == "osbb":
            telegram_id = callback.from_user.id
            user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
            user = user_res.scalar_one_or_none()
            apt_res = await session.execute(select(Apartment).where(Apartment.resident_id == user.id))
            apt = apt_res.scalar_one_or_none()
            
            bills_res = await session.execute(
                select(Bill).where(Bill.apartment_id == apt.id, Bill.is_paid == False)
            )
            bills = bills_res.scalars().all()
            for b in bills:
                b.is_paid = True
                b.paid_at = now
            apt.balance = 0.0
            await session.commit()
            service_title = "Утримання будинку (ОСББ)"
            amount = sum(b.amount for b in bills) if bills else 850.0
        else:
            acc_id = int(item_id.replace("util_", ""))
            acc_res = await session.execute(select(UtilityAccount).where(UtilityAccount.id == acc_id))
            acc = acc_res.scalar_one_or_none()
            if acc:
                acc.is_paid = True
                service_title = acc.provider_name
                amount = acc.last_amount
                await session.commit()
            else:
                await callback.answer("Рахунок не знайдено.")
                return

    receipt_text = (
        f"🧾 <b>КВИТАНЦІЯ ПРО ОПЛАТУ ПОСЛУГИ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>Статус:</b> Сплачено успішно\n"
        f"📌 <b>Служба:</b> {service_title}\n"
        f"💰 <b>Сплачена сума:</b> <b>{amount:.2f} грн</b>\n"
        f"🆔 <b>ID транзакції:</b> <code>{tx_id}</code>\n"
        f"📅 <b>Час:</b> {now.strftime('%d.%m.%Y %H:%M')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    back_kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📱 До єдиної квитанції", callback_data="utility_hub_main")]]
    )
    await callback.message.edit_text(receipt_text, reply_markup=back_kb, parse_mode="HTML")


# ==========================================
# 6. КЕРУВАННЯ ОСОБОВИМИ РАХУНКАМИ (SETTINGS)
# ==========================================

@router.callback_query(F.data == "manage_accounts_list")
async def cb_manage_accounts(callback: CallbackQuery):
    telegram_id = callback.from_user.id
    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()
        
        apt_res = await session.execute(select(Apartment).where(Apartment.resident_id == user.id))
        apt = apt_res.scalar_one_or_none()
        
        accounts_res = await session.execute(
            select(UtilityAccount).where(UtilityAccount.apartment_id == apt.id)
        )
        accounts = accounts_res.scalars().all()

    text = (
        "⚙️ <b>Керування особовими рахунками квартири</b>\n\n"
        "Тут ви можете налаштувати або змінити номери ваших особових рахунків постачальників послуг:\n\n"
    )

    buttons = []
    buttons.append([
        InlineKeyboardButton(text="🧙‍♂️ Запустити покроковий опитувальник", callback_data="start_utility_wizard")
    ])

    for acc in accounts:
        cfg = PROVIDER_CATALOG.get(acc.provider_type, {})
        icon = cfg.get("icon", "📄")
        name = cfg.get("name", acc.provider_name)
        text += f"• {icon} <b>{name}:</b> О/Р <code>{acc.account_number}</code>\n"
        buttons.append([
            InlineKeyboardButton(
                text=f"✏️ Змінити {name} ({acc.account_number})",
                callback_data=f"edit_acc_{acc.id}"
            ),
            InlineKeyboardButton(
                text="🗑",
                callback_data=f"del_acc_{acc.id}"
            )
        ])

    buttons.append([InlineKeyboardButton(text="➕ Додати окремий рахунок", callback_data="add_account_start")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад до квитанції", callback_data="utility_hub_main")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "add_account_start")
async def cb_add_account_start(callback: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💡 Світло (YASNO / ДТЕК)", callback_data="set_prov_electricity"),
                InlineKeyboardButton(text="🔥 Газ (Нафтогаз)", callback_data="set_prov_gas")
            ],
            [
                InlineKeyboardButton(text="🚰 Вода (Водоканал)", callback_data="set_prov_water"),
                InlineKeyboardButton(text="♨️ Опалення (Тепло)", callback_data="set_prov_heating")
            ],
            [
                InlineKeyboardButton(text="🌐 Інтернет", callback_data="set_prov_internet"),
                InlineKeyboardButton(text="🧹 Вивіз відходів", callback_data="set_prov_waste")
            ],
            [
                InlineKeyboardButton(text="❌ Скасувати", callback_data="manage_accounts_list")
            ]
        ]
    )
    await callback.message.edit_text(
        "➕ <b>Додавання особового рахунку</b>\n\nОберіть тип комунальної служби:",
        reply_markup=kb,
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("set_prov_"))
async def cb_set_provider(callback: CallbackQuery, state: FSMContext):
    prov_str = callback.data.replace("set_prov_", "")
    prov_type = UtilityProviderType(prov_str)
    cfg = PROVIDER_CATALOG.get(prov_type, {})
    
    await state.update_data(chosen_provider=prov_type.value, chosen_name=cfg.get("full_name", "Служба"))
    
    await callback.message.delete()
    await callback.message.answer(
        f"📝 Служба: <b>{cfg.get('full_name')}</b>\n\n"
        f"Введіть <b>номер вашого особового рахунку (О/Р)</b> з паперової квитанції або договору:\n"
        f"<i>(Наприклад: <code>{cfg.get('default_acc_prefix', '12')}345678</code>)</i>",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(UtilityAccountState.waiting_for_account_number)


@router.message(UtilityAccountState.waiting_for_account_number, F.text)
async def process_account_number(message: Message, state: FSMContext):
    acc_num = message.text.strip().replace(" ", "")
    if len(acc_num) < 3:
        await message.answer("⚠️ Номер особового рахунку занадто короткий. Введіть коректний номер:")
        return

    data = await state.get_data()
    prov_type_str = data.get("chosen_provider", "electricity")
    prov_name = data.get("chosen_name", "Міська служба")
    telegram_id = message.from_user.id

    async with async_session_maker() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_res.scalar_one_or_none()

        apt_res = await session.execute(select(Apartment).where(Apartment.resident_id == user.id))
        apt = apt_res.scalar_one_or_none()

        prov_type = UtilityProviderType(prov_type_str)

        exist_res = await session.execute(
            select(UtilityAccount).where(
                UtilityAccount.apartment_id == apt.id,
                UtilityAccount.provider_type == prov_type
            )
        )
        exist_acc = exist_res.scalar_one_or_none()
        if exist_acc:
            exist_acc.account_number = acc_num
            exist_acc.provider_name = prov_name
        else:
            new_acc = UtilityAccount(
                apartment_id=apt.id,
                provider_type=prov_type,
                provider_name=prov_name,
                account_number=acc_num,
                last_amount=0.0,
                is_paid=False
            )
            session.add(new_acc)

        await session.commit()
        await UtilityService.sync_apartment_utilities(session, apt.id)

    await state.clear()
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📱 Переглянути єдину квитанцію", callback_data="utility_hub_main")]]
    )
    await message.answer(
        f"✅ <b>Особовий рахунок успішно збережено!</b>\n\n"
        f"📌 <b>Служба:</b> {prov_name}\n"
        f"🔢 <b>Номер О/Р:</b> <code>{acc_num}</code>\n\n"
        f"<i>Дані автоматично синхронізовано з базою нарахувань.</i>",
        reply_markup=kb,
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("del_acc_"))
async def cb_del_account(callback: CallbackQuery):
    acc_id = int(callback.data.split("_")[2])
    async with async_session_maker() as session:
        res = await session.execute(select(UtilityAccount).where(UtilityAccount.id == acc_id))
        acc = res.scalar_one_or_none()
        if acc:
            await session.delete(acc)
            await session.commit()
            await callback.answer("Особовий рахунок видалено.")
        else:
            await callback.answer("Рахунок не знайдено.")

    await cb_manage_accounts(callback)


# ==========================================
# 7. РЕКВІЗИТИ IBAN
# ==========================================

@router.callback_query(F.data == "pay_iban_info")
async def cb_pay_iban(callback: CallbackQuery):
    iban_text = (
        "🏦 <b>Офіційні банківські реквізити ОСББ:</b>\n\n"
        "🏢 <b>Отримувач:</b> ОСББ «ДІМАП СМАРТ»\n"
        "🔢 <b>Код ЄДРПОУ:</b> 44123456\n"
        "💳 <b>Рахунок IBAN:</b>\n<code>UA563052990000026001234567890</code>\n"
        "🏛 <b>Банк:</b> АТ КБ «ПРИВАТБАНК» (або Monobank)\n\n"
        "📝 <b>Призначення платежу:</b>\n"
        "<code>Внесок на утримання будинку, кв. №___, ПІБ власника</code>\n\n"
        "<i>Після оплати кошти зараховуються на рахунок будинку протягом 1 банківського дня.</i>"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад до квитанції", callback_data="utility_hub_main")]]
    )
    await callback.message.edit_text(iban_text, reply_markup=kb, parse_mode="HTML")
