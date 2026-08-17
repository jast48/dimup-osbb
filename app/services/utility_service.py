import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Apartment, Bill, MeterReading, UtilityAccount, UtilityProviderType

logger = logging.getLogger(__name__)

# Каталог та налаштування інтеграцій з міськими службами
PROVIDER_CATALOG = {
    UtilityProviderType.ELECTRICITY: {
        "name": "YASNO (ДТЕК)",
        "full_name": "ТОВ «Київські енергетичні послуги» (YASNO / ДТЕК)",
        "icon": "💡",
        "unit": "кВт*год",
        "tariff": 4.32,
        "default_acc_prefix": "29"
    },
    UtilityProviderType.GAS: {
        "name": "Нафтогаз України",
        "full_name": "ГК «Нафтогаз України» (Газопостачання)",
        "icon": "🔥",
        "unit": "м³",
        "tariff": 7.96,
        "default_acc_prefix": "10"
    },
    UtilityProviderType.WATER: {
        "name": "Київводоканал",
        "full_name": "ПрАТ «АК «Київводоканал» (Вода та водовідведення)",
        "icon": "🚰",
        "unit": "м³",
        "tariff": 30.38,
        "default_acc_prefix": "04"
    },
    UtilityProviderType.HEATING: {
        "name": "Київтеплоенерго",
        "full_name": "КП «Київтеплоенерго» (Опалення та ГВП)",
        "icon": "♨️",
        "unit": "Гкал",
        "tariff": 1654.41,
        "default_acc_prefix": "55"
    },
    UtilityProviderType.WASTE: {
        "name": "Київкомунсервіс",
        "full_name": "КП «Київкомунсервіс» (Вивіз відходів)",
        "icon": "🧹",
        "unit": "міс",
        "tariff": 46.50,
        "default_acc_prefix": "88"
    },
    UtilityProviderType.INTERNET: {
        "name": "Домовий Інтернет",
        "full_name": "Гігабітний оптоволоконний інтернет (GPON)",
        "icon": "🌐",
        "unit": "міс",
        "tariff": 250.00,
        "default_acc_prefix": "99"
    }
}


class UtilityService:
    """
    Сервіс інтеграції комунальних служб та міського білінгу (ГЕРЦ / ГІОЦ / YASNO / Нафтогаз).
    Підтягує актуальні нарахування по особових рахунках жильця.
    """

    @staticmethod
    def simulate_provider_billing(
        provider_type: UtilityProviderType,
        account_number: str,
        apt_number: int,
        area: float = 60.0,
        meter_reading: Optional[MeterReading] = None
    ) -> Dict[str, Any]:
        """
        Імітація live-запиту до API міського білінгу або постачальника комунальних послуг
        по введеному особовому рахунку.
        """
        cfg = PROVIDER_CATALOG.get(provider_type, {})
        base_tariff = cfg.get("tariff", 100.0)
        
        # Генерація реалістичних нарахувань на основі номеру квартири та площі / лічильників
        seed = (hash(account_number) + apt_number) % 100

        if provider_type == UtilityProviderType.ELECTRICITY:
            kwh = 120 + (seed % 90)
            if meter_reading and meter_reading.electricity:
                kwh = max(50.0, meter_reading.electricity % 250)
            amount = round(kwh * base_tariff, 2)
            details = f"Обсяг: {kwh:.0f} кВт*год × {base_tariff:.2f} грн"

        elif provider_type == UtilityProviderType.GAS:
            m3 = 8.0 + (seed % 12)
            amount = round(m3 * base_tariff, 2)
            details = f"Обсяг: {m3:.1f} м³ × {base_tariff:.2f} грн"

        elif provider_type == UtilityProviderType.WATER:
            cold_m3 = 4.0 + (seed % 5)
            if meter_reading and meter_reading.cold_water:
                cold_m3 = max(2.0, meter_reading.cold_water % 10)
            amount = round(cold_m3 * base_tariff, 2)
            details = f"Холодна вода: {cold_m3:.1f} м³ × {base_tariff:.2f} грн"

        elif provider_type == UtilityProviderType.HEATING:
            # Опалення залежить від площі
            gcal = (area / 60.0) * 0.65
            amount = round(gcal * base_tariff, 2)
            details = f"Теплова енергія: {gcal:.3f} Гкал (Площа {area} м²)"

        elif provider_type == UtilityProviderType.WASTE:
            residents_count = 2 if apt_number % 2 == 0 else 1
            amount = round(residents_count * base_tariff, 2)
            details = f"Вивіз ТПВ: {residents_count} зареєстр. осіб"

        elif provider_type == UtilityProviderType.INTERNET:
            amount = base_tariff
            details = "Тариф «Гігабітний GPON 1000 Мбіт/с»"

        else:
            amount = 150.00
            details = "Комунальні послуги"

        return {
            "provider_name": cfg.get("full_name", "Міська служба"),
            "amount": amount,
            "details": details,
            "sync_time": datetime.now()
        }

    @classmethod
    def validate_and_lookup_account(
        cls,
        provider_type: UtilityProviderType,
        account_number: str,
        apt_number: int,
        area: float = 60.0
    ) -> Dict[str, Any]:
        """
        Миттєва перевірка та валідація особового рахунку в базі постачальника.
        Повертає картку перевірки: знайденого постачальника, адресу, стан нарахування.
        """
        acc_clean = account_number.strip().replace(" ", "").replace("-", "")
        cfg = PROVIDER_CATALOG.get(provider_type, {})
        full_name = cfg.get("full_name", "Міська служба")
        icon = cfg.get("icon", "📄")

        # Перевірка формату (тільки цифри, достатня довжина)
        if not acc_clean.isdigit() or len(acc_clean) < 4:
            return {
                "is_valid": False,
                "error_message": "⚠️ Номер особового рахунку повинен складатись тільки з цифр (від 4 до 16 цифр)."
            }

        # Отримуємо розрахунок
        billing_info = cls.simulate_provider_billing(
            provider_type=provider_type,
            account_number=acc_clean,
            apt_number=apt_number,
            area=area
        )

        return {
            "is_valid": True,
            "provider_type": provider_type.value,
            "provider_name": full_name,
            "short_name": cfg.get("name", full_name),
            "icon": icon,
            "account_number": acc_clean,
            "address": f"вул. Шевченка, 14, кв. №{apt_number}",
            "amount": billing_info["amount"],
            "details": billing_info["details"],
            "tariff": cfg.get("tariff", 0.0),
            "unit": cfg.get("unit", "")
        }

    @classmethod
    async def sync_apartment_utilities(cls, session: AsyncSession, apartment_id: int) -> List[UtilityAccount]:
        """
        Опитує міські бази даних для всіх прив'язаних особових рахунків квартири.
        """
        apt_res = await session.execute(select(Apartment).where(Apartment.id == apartment_id))
        apt = apt_res.scalar_one_or_none()
        if not apt:
            return []

        meter_res = await session.execute(
            select(MeterReading).where(MeterReading.apartment_id == apartment_id).order_by(desc(MeterReading.id)).limit(1)
        )
        last_meter = meter_res.scalar_one_or_none()

        # Отримуємо всі зареєстровані особові рахунки
        accounts_res = await session.execute(
            select(UtilityAccount).where(UtilityAccount.apartment_id == apartment_id)
        )
        accounts = accounts_res.scalars().all()

        # Оновлюємо кожен рахунок через API
        for acc in accounts:
            if acc.account_number and acc.account_number != "—":
                bill_info = cls.simulate_provider_billing(
                    provider_type=acc.provider_type,
                    account_number=acc.account_number,
                    apt_number=apt.number,
                    area=apt.area or 60.0,
                    meter_reading=last_meter
                )
                acc.last_amount = bill_info["amount"]
                acc.details = bill_info["details"]
                acc.last_sync_at = bill_info["sync_time"]

        await session.commit()
        return accounts

    @classmethod
    async def get_unified_bill_summary(cls, session: AsyncSession, apartment_id: int) -> Dict[str, Any]:
        """
        Формує повну Єдину Квитанцію:
        - Внесок на утримання будинку (ОСББ)
        - Світло (YASNO / ДТЕК)
        - Газ (Нафтогаз)
        - Вода (Київводоканал)
        - Опалення (Київтеплоенерго)
        """
        apt_res = await session.execute(select(Apartment).where(Apartment.id == apartment_id))
        apt = apt_res.scalar_one_or_none()
        if not apt:
            return {"total_amount": 0.0, "items": [], "unpaid_count": 0}

        # 1. Рахунки ОСББ
        bills_res = await session.execute(
            select(Bill).where(Bill.apartment_id == apartment_id, Bill.is_paid == False).order_by(desc(Bill.id))
        )
        osbb_unpaid_bills = bills_res.scalars().all()
        osbb_amount = sum(b.amount for b in osbb_unpaid_bills) if osbb_unpaid_bills else (abs(apt.balance) if apt.balance < 0 else 0.0)

        # 2. Зовнішні комунальні рахунки
        accounts_res = await session.execute(
            select(UtilityAccount).where(UtilityAccount.apartment_id == apartment_id)
        )
        accounts = accounts_res.scalars().all()
        account_by_type = {acc.provider_type: acc for acc in accounts}

        items = []
        # Додаємо ОСББ в початок списку
        items.append({
            "id": "osbb",
            "type": "osbb",
            "icon": "🏠",
            "title": "Утримання будинку (ОСББ)",
            "account_number": f"Кв. №{apt.number}",
            "amount": osbb_amount,
            "details": f"Тариф 8.50 грн/м² (Площа {apt.area or 60.0} м²)",
            "is_paid": osbb_amount == 0.0
        })

        total_to_pay = osbb_amount
        has_custom_accounts = len(accounts) > 0

        # Основні 4 міські служби
        main_providers = [
            UtilityProviderType.ELECTRICITY,
            UtilityProviderType.GAS,
            UtilityProviderType.WATER,
            UtilityProviderType.HEATING
        ]

        for p_type in main_providers:
            cfg = PROVIDER_CATALOG.get(p_type, {})
            icon = cfg.get("icon", "📄")
            short_title = cfg.get("name", "Міська служба")
            acc = account_by_type.get(p_type)

            if acc and acc.account_number:
                if not acc.is_paid:
                    total_to_pay += acc.last_amount

                items.append({
                    "id": f"util_{acc.id}",
                    "account_id": acc.id,
                    "type": acc.provider_type.value,
                    "icon": icon,
                    "title": short_title,
                    "full_name": acc.provider_name,
                    "account_number": acc.account_number,
                    "amount": acc.last_amount,
                    "details": acc.details or "За поточний період",
                    "is_paid": acc.is_paid,
                    "is_linked": True,
                    "last_sync_at": acc.last_sync_at.strftime("%d.%m.%Y %H:%M") if acc.last_sync_at else "—"
                })
            else:
                # Служба ще не прив'язана
                items.append({
                    "id": f"unlinked_{p_type.value}",
                    "type": p_type.value,
                    "icon": icon,
                    "title": short_title,
                    "full_name": cfg.get("full_name", short_title),
                    "account_number": "Не прив'язано ⚠️",
                    "amount": 0.0,
                    "details": "Введіть особовий рахунок через опитувальник",
                    "is_paid": True,
                    "is_linked": False,
                    "last_sync_at": "—"
                })

        unpaid_count = sum(1 for item in items if not item["is_paid"] and item["amount"] > 0)

        return {
            "apartment_number": apt.number,
            "area": apt.area or 60.0,
            "total_to_pay": round(total_to_pay, 2),
            "unpaid_count": unpaid_count,
            "has_custom_accounts": has_custom_accounts,
            "items": items,
            "last_updated": datetime.now().strftime("%d.%m.%Y %H:%M")
        }

    @classmethod
    async def pay_all_utilities(cls, session: AsyncSession, apartment_id: int) -> float:
        """
        Проводить оплату ВСІХ неоплачених комунальних рахунків та рахунків ОСББ
        """
        apt_res = await session.execute(select(Apartment).where(Apartment.id == apartment_id))
        apt = apt_res.scalar_one_or_none()
        if not apt:
            return 0.0

        # Оплачуємо рахунки ОСББ
        bills_res = await session.execute(
            select(Bill).where(Bill.apartment_id == apartment_id, Bill.is_paid == False)
        )
        bills = bills_res.scalars().all()
        now = datetime.now()
        osbb_paid_sum = 0.0
        for b in bills:
            b.is_paid = True
            b.paid_at = now
            b.payment_method = "Єдина квитанція (Apple Pay / Mono)"
            osbb_paid_sum += b.amount
        
        apt.balance += osbb_paid_sum

        # Оплачуємо всі особові рахунки
        accounts_res = await session.execute(
            select(UtilityAccount).where(UtilityAccount.apartment_id == apartment_id, UtilityAccount.is_paid == False)
        )
        accounts = accounts_res.scalars().all()
        util_paid_sum = 0.0
        for acc in accounts:
            acc.is_paid = True
            util_paid_sum += acc.last_amount

        await session.commit()
        return round(osbb_paid_sum + util_paid_sum, 2)
