from typing import Optional
from datetime import date, datetime
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.base import Base


class AnalystReport(Base):
    """네이버 금융 애널리스트 리포트 PDF 메타데이터."""

    __tablename__ = "analyst_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    firm_name: Mapped[str] = mapped_column(String(100), nullable=False)
    analyst_name: Mapped[Optional[str]] = mapped_column(String(100))
    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    pdf_url: Mapped[str] = mapped_column(String(500), nullable=False)
    pdf_path: Mapped[Optional[str]] = mapped_column(String(500))   # 로컬 저장 경로
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # RAG 색인 여부
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # relationships
    stock: Mapped["Stock"] = relationship(back_populates="analyst_reports")  # noqa: F821
    opinions: Mapped[list["AnalystOpinion"]] = relationship(back_populates="report")


class AnalystOpinion(Base):
    """리포트에서 추출한 투자의견 및 목표주가."""

    __tablename__ = "analyst_opinions"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("analyst_reports.id"), nullable=False, index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    opinion: Mapped[Optional[str]] = mapped_column(String(20))       # Buy / Hold / Sell / Neutral
    price_target: Mapped[Optional[float]] = mapped_column(Float)
    prev_price_target: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # relationships
    report: Mapped["AnalystReport"] = relationship(back_populates="opinions")
    stock: Mapped["Stock"] = relationship(back_populates="analyst_opinions")  # noqa: F821
