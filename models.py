from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class EmployeeRole(str, Enum):
    MOTORISTA = "MOTORISTA"
    AJUDANTE = "AJUDANTE"


class SubmissionStatus(str, Enum):
    ENVIADO = "ENVIADO"
    APROVADO = "APROVADO"
    REJEITADO = "REJEITADO"


class BenefitType(str, Enum):
    NONE = "NONE"
    DIARIA = "DIARIA"
    TICKET = "TICKET"


def enum_type(enum_class: type[Enum], name: str) -> SAEnum:
    return SAEnum(
        enum_class,
        name=name,
        native_enum=False,
        values_callable=lambda enum: [item.value for item in enum],
        validate_strings=True,
    )


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    role: Mapped[EmployeeRole] = mapped_column(enum_type(EmployeeRole, "employee_role"))
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    submissions: Mapped[list[RdvSubmission]] = relationship(back_populates="employee")


class RdvPeriod(Base):
    __tablename__ = "rdv_periods"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_period_dates"),
        Index(
            "uq_one_active_period",
            "active",
            unique=True,
            sqlite_where=text("active = 1"),
            postgresql_where=text("active"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    submissions: Mapped[list[RdvSubmission]] = relationship(back_populates="period")


class RdvSubmission(Base):
    __tablename__ = "rdv_submissions"
    __table_args__ = (
        UniqueConstraint(
            "employee_id", "period_id", name="uq_submission_employee_period"
        ),
        CheckConstraint(
            "advance_amount >= 0", name="ck_submission_advance_nonnegative"
        ),
        Index("ix_submission_status_submitted", "status", "submitted_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    period_id: Mapped[int] = mapped_column(ForeignKey("rdv_periods.id"), nullable=False)
    advance_received: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    advance_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    status: Mapped[SubmissionStatus] = mapped_column(
        enum_type(SubmissionStatus, "submission_status"), nullable=False
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    admin_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    employee: Mapped[Employee] = relationship(back_populates="submissions")
    period: Mapped[RdvPeriod] = relationship(back_populates="submissions")
    entries: Mapped[list[RdvEntry]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
        order_by="RdvEntry.date",
    )


class RdvEntry(Base):
    __tablename__ = "rdv_entries"
    __table_args__ = (
        UniqueConstraint("submission_id", "date", name="uq_entry_submission_date"),
        CheckConstraint("hotel_amount >= 0", name="ck_entry_hotel_nonnegative"),
        CheckConstraint("benefit_amount >= 0", name="ck_entry_benefit_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("rdv_submissions.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    hotel_name: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    hotel_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    benefit_type: Mapped[BenefitType] = mapped_column(
        enum_type(BenefitType, "benefit_type"), nullable=False
    )
    benefit_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    submission: Mapped[RdvSubmission] = relationship(back_populates="entries")
