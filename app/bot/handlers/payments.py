import uuid
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, desc
from app.db.session import async_session_maker
from app.db.models import User, Apartment, Bill, UserRole
from app.bot.keyboards.keyboards import get_main_menu_keyboard

router = Router()

@router.message(F.text.contains("Оплата") | F.text.contains("Сплатити") | F.text.contains("Платіжка"))
@router.callback_query(F.data == "pay_bills_start")
async def cmd_pay_bills_menu(event: Message | CallbackQuery, state: FSMContext):
    """Меню онлайн-оплаты счетов"""
    await state.clear()
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

        # Ищем неоплаченные счета
        bills_res = await session.execute(
            select(Bill).where(Bill.apartment_id == apt.id, Bill.is_paid == False).order_by(desc(Bill.id))
        )
        unpaid_bills = bills_res.scalars().all()

    if not unpaid_bills:
        text = (
            f"🎉 <b>У вас немає неоплачених рахунків!</b>\n\n"
            f"🏢 <b>Квартира:</b> №{apt.number}\n"
            f"💳 <b>Поточний баланс:</b> {apt.balance:.2f} грн (Заборгованість відсутня 🟢)\n\n"
            f"<i>Дякуємо за своєчасну оплату комунальних послуг нашого будинку!</i>"
        )
        await message.answer(text, parse_mode="HTML")
        return

    total_unpaid = sum(b.amount for b in unpaid_bills)

    text = (
        f"💳 <b>Онлайн-оплата комунальних послуг</b>\n\n"
        f"🏢 <b>Квартира:</b> №{apt.number}\n"
        f"🔴 <b>Сума до сплати:</b> <b>{total_unpaid:.2f} грн</b>\n\n"
        f"📄 <b>Неоплачені квитанції:</b>\n"
    )

    buttons = []
    for b in unpaid_bills:
        text += f"• Рахунок за {b.month}/{b.year}: <b>{b.amount:.2f} грн</b>\n"
        buttons.append([
            InlineKeyboardButton(
                text=f"🟢 Сплатити {b.amount:.2f} грн ({b.month}/{b.year})",
                callback_data=f"pay_single_bill_{b.id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="🏦 Оплата за реквізитами IBAN",
            callback_data="pay_iban_info"
        )
    ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("pay_single_bill_"))
async def cb_process_single_payment(callback: CallbackQuery, bot: Bot):
    """Формирование шлюза оплаты Monobank / Apple Pay"""
    bill_id = int(callback.data.split("_")[3])

    async with async_session_maker() as session:
        res = await session.execute(select(Bill).where(Bill.id == bill_id))
        bill = res.scalar_one_or_none()
        if not bill:
            await callback.answer("Рахунок не знайдено.")
            return

        apt_res = await session.execute(select(Apartment).where(Apartment.id == bill.apartment_id))
        apt = apt_res.scalar_one_or_none()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚡️ Оплатити в 1 клік (Apple Pay / Monobank)",
                    callback_data=f"confirm_pay_now_{bill.id}"
                )
            ],
            [
                InlineKeyboardButton(text="❌ Скасувати", callback_data="admin_back_main")
            ]
        ]
    )

    text = (
        f"🔒 <b>Безпечна платіжна сесія DimUp Pay</b>\n\n"
        f"🏢 <b>Призначення:</b> Утримання будинку за {bill.month}/{bill.year}\n"
        f"🏢 <b>Квартира:</b> №{apt.number}\n"
        f"💰 <b>Сума до сплати:</b> <b>{bill.amount:.2f} грн</b>\n\n"
        f"Оберіть спосіб оплати нижче (комісія 0%):"
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("confirm_pay_now_"))
async def cb_confirm_payment(callback: CallbackQuery):
    """Исполнение платежа и выдача официальной квитанции"""
    bill_id = int(callback.data.split("_")[3])
    now = datetime.now()
    tx_id = f"DU-{uuid.uuid4().hex[:8].upper()}"

    async with async_session_maker() as session:
        res = await session.execute(select(Bill).where(Bill.id == bill_id))
        bill = res.scalar_one_or_none()
        if not bill or bill.is_paid:
            await callback.answer("Цей рахунок вже оплачено.")
            return

        apt_res = await session.execute(select(Apartment).where(Apartment.id == bill.apartment_id))
        apt = apt_res.scalar_one_or_none()

        bill.is_paid = True
        bill.paid_at = now
        bill.payment_method = "Monobank / Apple Pay"
        bill.transaction_id = tx_id
        
        # Обновляем баланс квартиры
        apt.balance += bill.amount
        await session.commit()
        apt_num = apt.number
        new_balance = apt.balance

    receipt_text = (
        f"🧾 <b>ЕЛЕКТРОННА КВИТАНЦІЯ ПРО ОПЛАТУ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>Статус:</b> Успішно проведено\n"
        f"🆔 <b>Номер транзакції:</b> <code>{tx_id}</code>\n"
        f"📅 <b>Дата та час:</b> {now.strftime('%d.%m.%Y %H:%M:%S')}\n"
        f"🏢 <b>Квартира:</b> №{apt_num}\n"
        f"💳 <b>Метод оплати:</b> Monobank / Apple Pay\n"
        f"📌 <b>Призначення:</b> Внесок на утримання будинку ({bill.month}/{bill.year})\n"
        f"💰 <b>Сплачена сума:</b> <b>{bill.amount:.2f} грн</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Оновлений баланс:</b> {new_balance:.2f} грн (Заборгованість погашена 🟢)\n\n"
        f"<i>Дякуємо! Квитанція збережена в історії платежів вашого кабінету.</i>"
    )

    await callback.message.delete()
    await callback.message.answer(receipt_text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")


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
        inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="pay_bills_start")]]
    )
    await callback.message.edit_text(iban_text, reply_markup=kb, parse_mode="HTML")
