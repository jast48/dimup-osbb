from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import async_session_maker
from app.db.models import Apartment, Bill, Poll, PollOption, Ticket

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@router.get("/webapp")
async def render_webapp(request: Request, apt_num: int = 1):
    """
    Отображение личного кабинета жителя в Telegram WebApp
    """
    async with async_session_maker() as session:
        # Получаем данные квартиры
        apt_res = await session.execute(
            select(Apartment).where(Apartment.number == apt_num)
        )
        apartment = apt_res.scalar_one_or_none()

        # Получаем начисления (Bills)
        bills = []
        if apartment:
            bills_res = await session.execute(
                select(Bill).where(Bill.apartment_id == apartment.id)
            )
            bills = bills_res.scalars().all()

        # Получаем активные опросы вместе с вариантами и голосами (полный Eager Load)
        polls_res = await session.execute(
            select(Poll).options(
                selectinload(Poll.options).selectinload(PollOption.votes)
            ).where(Poll.is_active == True)
        )
        polls = polls_res.scalars().all()

        # Получаем заявки
        tickets = []
        if apartment:
            tickets_res = await session.execute(
                select(Ticket).where(Ticket.apartment_id == apartment.id)
            )
            tickets = tickets_res.scalars().all()

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "apt": apartment,
            "bills": bills,
            "polls": polls,
            "tickets": tickets
        }
    )
