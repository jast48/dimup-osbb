import asyncio
import logging
from sqlalchemy import select, text
from app.db.session import engine, Base, async_session_maker
from app.db.models import (
    User, UserRole,
    Apartment,
    Ticket, TicketCategory, TicketUrgency, TicketStatus,
    Announcement,
    Poll, PollOption,
    Bill, MeterReading, ServiceOrder
)

logger = logging.getLogger(__name__)

async def init_database():
    """
    Создает все таблицы в базе данных (если их еще нет)
    и заполняет базу тестовыми начальными данными (Seed data).
    """
    async with engine.begin() as conn:
        # Создаем все таблицы
        await conn.run_sync(Base.metadata.create_all)
        
        # Безопасное добавление новых колонок для SQLite
        migration_statements = [
            "ALTER TABLE tickets ADD COLUMN audio_file_id VARCHAR(255)",
            "ALTER TABLE tickets ADD COLUMN rating INTEGER",
            "ALTER TABLE tickets ADD COLUMN review TEXT",
            "ALTER TABLE bills ADD COLUMN payment_method VARCHAR(50)",
            "ALTER TABLE bills ADD COLUMN transaction_id VARCHAR(100)"
        ]
        for col_def in migration_statements:
            try:
                await conn.execute(text(col_def))
            except Exception:
                pass # Колонка уже существует

    # Наполняем тестовыми данными (квартиры 1-20, объявление, опрос)
    async with async_session_maker() as session:
        result = await session.execute(select(Apartment))
        existing_apartments = result.scalars().all()

        if not existing_apartments:
            apartments = []
            for num in range(1, 21):
                floor = ((num - 1) // 4) + 1
                entrance = 1
                area = 45.0 + (num % 3) * 15.0
                balance = 0.0 if num % 5 != 0 else -650.0
                
                apt = Apartment(
                    number=num,
                    floor=floor,
                    entrance=entrance,
                    area=area,
                    balance=balance
                )
                apartments.append(apt)
            session.add_all(apartments)
            await session.flush()

            announcement = Announcement(
                title="Планова перевірка системи опалення",
                content="Шановні мешканці! У вівторок з 10:00 до 16:00 буде проводитися планова перевірка тиску в системі опалення. Прохання бути уважними.",
                is_emergency=False
            )
            session.add(announcement)

            poll = Poll(
                title="Встановлення шлагбауму на в'їзді у двір",
                description="Пропонується встановити автоматичний шлагбаум із GSM-модулем та системою розпізнавання номерів для безпеки нашого двору."
            )
            session.add(poll)
            await session.flush()

            options = [
                PollOption(poll_id=poll.id, text="Так, підтримую встановлення"),
                PollOption(poll_id=poll.id, text="Ні, я проти"),
                PollOption(poll_id=poll.id, text="Потрібно більше інформації щодо вартості")
            ]
            session.add_all(options)

            bills = [
                Bill(apartment_id=apartments[0].id, month=8, year=2026, amount=850.0, is_paid=True),
                Bill(apartment_id=apartments[4].id, month=8, year=2026, amount=920.0, is_paid=False),
            ]
            session.add_all(bills)

            await session.commit()
            print("Database initialized and sample data seeded successfully!")

if __name__ == "__main__":
    asyncio.run(init_database())
