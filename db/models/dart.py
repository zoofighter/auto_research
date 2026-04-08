from datetime import date, datetime
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.base import Base


class DartDisclosure(Base):
    """DART 공시 데이터."""

    __tablename__ = "dart_disclosures"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    rcept_no: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)  # DART 접수번호
    disclosure_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # business_report / quarterly / major_event / fair_disclosure
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    corp_name: Mapped[str] = mapped_column(String(100), nullable=False)
    rcept_dt: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    url: Mapped[str | None] = mapped_column(String(500))
    summary: Mapped[str | None] = mapped_column(Text)
    is_major_event: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # relationships
    stock: Mapped["Stock"] = relationship(back_populates="dart_disclosures")  # noqa: F821
