import enum
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    BigInteger,
    String,
    Text,
    Float,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Enum as SQLEnum,
    func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base

# ==========================================
# 1. ПЕРЕЧИСЛЕНИЯ (ENUMS) ДЛЯ ТИПИЗАЦИИ
# ==========================================

class UserRole(str, enum.Enum):
    RESIDENT = "resident"
    BOARD = "board"
    CONTRACTOR = "contractor"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"

class TicketCategory(str, enum.Enum):
    PLUMBING = "plumbing"
    ELECTRICITY = "electricity"
    ELEVATOR = "elevator"
    CLEANING = "cleaning"
    SECURITY = "security"
    ROOF_FACADE = "roof_facade"
    OTHER = "other"

class TicketUrgency(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    EMERGENCY = "emergency"

class TicketStatus(str, enum.Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"

class ServiceOrderStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# ==========================================
# 2. ТАБЛИЦЫ БАЗЫ ДАННЫХ (ORM МОДЕЛИ)
# ==========================================

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole), default=UserRole.RESIDENT, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    apartments: Mapped[List["Apartment"]] = relationship("Apartment", back_populates="resident")
    created_tickets: Mapped[List["Ticket"]] = relationship("Ticket", foreign_keys="Ticket.creator_id", back_populates="creator")
    assigned_tickets: Mapped[List["Ticket"]] = relationship("Ticket", foreign_keys="Ticket.assigned_to_id", back_populates="assigned_master")
    service_orders: Mapped[List["ServiceOrder"]] = relationship("ServiceOrder", back_populates="user")


class Apartment(Base):
    __tablename__ = "apartments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    number: Mapped[int] = mapped_column(index=True, nullable=False)
    entrance: Mapped[Optional[int]] = mapped_column(nullable=True)
    floor: Mapped[Optional[int]] = mapped_column(nullable=True)
    area: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    balance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    
    resident_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    resident: Mapped[Optional["User"]] = relationship("User", back_populates="apartments")

    tickets: Mapped[List["Ticket"]] = relationship("Ticket", back_populates="apartment")
    bills: Mapped[List["Bill"]] = relationship("Bill", back_populates="apartment")
    meter_readings: Mapped[List["MeterReading"]] = relationship("MeterReading", back_populates="apartment")
    service_orders: Mapped[List["ServiceOrder"]] = relationship("ServiceOrder", back_populates="apartment")


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    apartment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("apartments.id"), nullable=True)
    
    category: Mapped[TicketCategory] = mapped_column(SQLEnum(TicketCategory), default=TicketCategory.OTHER)
    urgency: Mapped[TicketUrgency] = mapped_column(SQLEnum(TicketUrgency), default=TicketUrgency.NORMAL)
    status: Mapped[TicketStatus] = mapped_column(SQLEnum(TicketStatus), default=TicketStatus.NEW)
    
    description: Mapped[str] = mapped_column(Text, nullable=False)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    photo_file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    audio_file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    assigned_to_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    review: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    creator: Mapped["User"] = relationship("User", foreign_keys=[creator_id], back_populates="created_tickets")
    assigned_master: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assigned_to_id], back_populates="assigned_tickets")
    apartment: Mapped[Optional["Apartment"]] = relationship("Apartment", back_populates="tickets")


class ServiceOrder(Base):
    """Заказ платной услуги из маркетплейса мастеров"""
    __tablename__ = "service_orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    apartment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("apartments.id"), nullable=True)
    
    service_title: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="general")
    price_est: Mapped[float] = mapped_column(Float, default=0.0) # примерная стоимость
    
    preferred_time: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    status: Mapped[ServiceOrderStatus] = mapped_column(SQLEnum(ServiceOrderStatus), default=ServiceOrderStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="service_orders")
    apartment: Mapped[Optional["Apartment"]] = relationship("Apartment", back_populates="service_orders")


class MeterReading(Base):
    """Показания счетчиков квартиры (вода, свет, тепло)"""
    __tablename__ = "meter_readings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    apartment_id: Mapped[int] = mapped_column(ForeignKey("apartments.id"), nullable=False)
    month: Mapped[int] = mapped_column(nullable=False)
    year: Mapped[int] = mapped_column(nullable=False)
    
    cold_water: Mapped[float] = mapped_column(Float, default=0.0)
    hot_water: Mapped[float] = mapped_column(Float, default=0.0)
    electricity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    apartment: Mapped["Apartment"] = relationship("Apartment", back_populates="meter_readings")


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class Poll(Base):
    __tablename__ = "polls"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    options: Mapped[List["PollOption"]] = relationship("PollOption", back_populates="poll", cascade="all, delete-orphan")


class PollOption(Base):
    __tablename__ = "poll_options"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    poll_id: Mapped[int] = mapped_column(ForeignKey("polls.id"), nullable=False)
    text: Mapped[str] = mapped_column(String(200), nullable=False)
    
    poll: Mapped["Poll"] = relationship("Poll", back_populates="options")
    votes: Mapped[List["PollVote"]] = relationship("PollVote", back_populates="option", cascade="all, delete-orphan")


class PollVote(Base):
    __tablename__ = "poll_votes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    poll_id: Mapped[int] = mapped_column(ForeignKey("polls.id"), nullable=False)
    option_id: Mapped[int] = mapped_column(ForeignKey("poll_options.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    option: Mapped["PollOption"] = relationship("PollOption", back_populates="votes")


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    apartment_id: Mapped[int] = mapped_column(ForeignKey("apartments.id"), nullable=False)
    month: Mapped[int] = mapped_column(nullable=False)
    year: Mapped[int] = mapped_column(nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    payment_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True) # Monobank, Apple Pay, Google Pay, Card
    transaction_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    apartment: Mapped["Apartment"] = relationship("Apartment", back_populates="bills")
