import csv
import io
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Apartment, Bill, User


class BankSyncService:
    """Сервіс для автоматичного імпорту та рознесення банківських виписок (Приват24 / Monobank / Клієнт-Банк)"""

    @staticmethod
    def extract_apartment_number(purpose_text: str) -> Optional[int]:
        """Знаходить номер квартири в тексті призначення платежу за регулярними виразами"""
        if not purpose_text:
            return None
        
        patterns = [
            r'кв[.\s№]+(\d{1,4})\b',           # кв. 45, кв 45, кв.№45
            r'квартир[аиі][\s№]+(\d{1,4})\b',  # квартира 45, квартири 45
            r'о/?р[\s№:]*(\d{1,4})\b',         # о/р 45
            r'\b№\s*(\d{1,4})\b',              # № 45
            r'квартплат[аи][\s№]+(\d{1,4})\b', # квартплата 45
        ]
        
        for pattern in patterns:
            match = re.search(pattern, purpose_text, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue
        return None

    @classmethod
    async def process_bank_statement_csv(
        cls,
        session: AsyncSession,
        csv_content: str,
        delimiter: str = ";"
    ) -> Dict[str, Any]:
        """
        Обробляє CSV-виписку банку, ідентифікує квартири та автоматично закриває заборгованість.
        """
        # Спробуємо визначити розділювач (кома або крапка з комою)
        if ";" in csv_content[:200]:
            delimiter = ";"
        elif "," in csv_content[:200]:
            delimiter = ","
        
        reader = csv.reader(io.StringIO(csv_content), delimiter=delimiter)
        
        matched_records = []
        unmatched_records = []
        total_amount = 0.0

        for row_idx, row in enumerate(reader):
            if not row or row_idx == 0 and any("дата" in col.lower() or "сума" in col.lower() for col in row):
                continue # Пропускаємо заголовок
            
            # Шукаємо призначення платежу та суму в рядку
            row_str = " ".join(row)
            
            # Шукаємо числове значення суми (наприклад: 1250.00 або 1 250,50)
            amount = 0.0
            amount_found = False
            for col in row:
                col_cleaned = col.replace(" ", "").replace("UAH", "").replace("грн", "").replace(",", ".")
                try:
                    val = float(col_cleaned)
                    if val > 0:
                        amount = val
                        amount_found = True
                        break
                except ValueError:
                    continue

            if not amount_found or amount <= 0:
                continue

            apt_num = cls.extract_apartment_number(row_str)

            if apt_num:
                # Шукаємо квартиру в базі
                apt_res = await session.execute(select(Apartment).where(Apartment.number == apt_num))
                apt = apt_res.scalar_one_or_none()

                if apt:
                    # Зараховуємо кошти на баланс квартири
                    apt.balance += amount

                    # Шукаємо несплачені рахунки по цій квартирі
                    bills_res = await session.execute(
                        select(Bill).where(Bill.apartment_id == apt.id, Bill.is_paid == False)
                    )
                    unpaid_bills = bills_res.scalars().all()
                    
                    closed_bills_count = 0
                    for bill in unpaid_bills:
                        if amount >= bill.amount:
                            bill.is_paid = True
                            bill.paid_at = datetime.now()
                            bill.payment_method = "Bank Statement (Auto-sync)"
                            closed_bills_count += 1

                    matched_records.append({
                        "apartment_number": apt_num,
                        "amount": amount,
                        "new_balance": apt.balance,
                        "closed_bills": closed_bills_count,
                        "raw_purpose": row_str[:80]
                    })
                    total_amount += amount
                else:
                    unmatched_records.append({
                        "amount": amount,
                        "reason": f"Квартиру №{apt_num} не знайдено в базі будинку",
                        "raw": row_str[:80]
                    })
            else:
                unmatched_records.append({
                    "amount": amount,
                    "reason": "Не знайдено номер квартири в призначенні платежу",
                    "raw": row_str[:80]
                })

        await session.commit()

        return {
            "total_processed": len(matched_records) + len(unmatched_records),
            "matched_count": len(matched_records),
            "unmatched_count": len(unmatched_records),
            "total_credited_amount": round(total_amount, 2),
            "matched_records": matched_records,
            "unmatched_records": unmatched_records
        }
