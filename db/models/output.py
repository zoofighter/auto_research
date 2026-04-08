from typing import Optional
from datetime import date, datetime
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.base import Base


class GeneratedReport(Base):
    """최종 AI 생성 보고서."""

    __tablename__ = "generated_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("analysis_sessions.id"), nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    executive_summary: Mapped[Optional[str]] = mapped_column(Text)
    report_md_path: Mapped[Optional[str]] = mapped_column(String(500))
    report_pdf_path: Mapped[Optional[str]] = mapped_column(String(500))
    ppt_path: Mapped[Optional[str]] = mapped_column(String(500))
    quality_score: Mapped[Optional[float]] = mapped_column(Float)      # LLM 자체 평가 0.0~1.0
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # relationships
    stock: Mapped["Stock"] = relationship(back_populates="generated_reports")  # noqa: F821
    session: Mapped["AnalysisSession"] = relationship(back_populates="generated_reports")  # noqa: F821
    sources: Mapped[list["ReportSource"]] = relationship(back_populates="generated_report")


class ReportSource(Base):
    """보고서 출처 추적 — 환각 방지용 audit trail."""

    __tablename__ = "report_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    generated_report_id: Mapped[int] = mapped_column(
        ForeignKey("generated_reports.id"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # analyst_report / dart / news / web
    source_id: Mapped[Optional[int]] = mapped_column(Integer)          # 해당 테이블의 id
    excerpt: Mapped[Optional[str]] = mapped_column(Text)               # 인용 구절
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # relationships
    generated_report: Mapped["GeneratedReport"] = relationship(back_populates="sources")
