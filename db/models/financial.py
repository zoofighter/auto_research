from typing import Optional
from datetime import date, datetime
from sqlalchemy import Date, DateTime, Float, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.base import Base


class FinancialMetric(Base):
    """네이버 주식 재무 핵심 지표 스냅샷."""

    __tablename__ = "financial_metrics"
    __table_args__ = (UniqueConstraint("stock_id", "metric_date", name="uq_stock_metric_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    metric_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # 밸류에이션
    per: Mapped[Optional[float]] = mapped_column(Float)
    pbr: Mapped[Optional[float]] = mapped_column(Float)
    psr: Mapped[Optional[float]] = mapped_column(Float)
    ev_ebitda: Mapped[Optional[float]] = mapped_column(Float)

    # 수익성
    operating_margin: Mapped[Optional[float]] = mapped_column(Float)   # 영업이익률 (%)
    roe: Mapped[Optional[float]] = mapped_column(Float)
    roa: Mapped[Optional[float]] = mapped_column(Float)
    ebitda_margin: Mapped[Optional[float]] = mapped_column(Float)

    # 성장성 (YoY %)
    revenue_yoy: Mapped[Optional[float]] = mapped_column(Float)
    op_income_yoy: Mapped[Optional[float]] = mapped_column(Float)
    eps_growth: Mapped[Optional[float]] = mapped_column(Float)

    # 안정성
    debt_ratio: Mapped[Optional[float]] = mapped_column(Float)         # 부채비율 (%)
    current_ratio: Mapped[Optional[float]] = mapped_column(Float)      # 유동비율 (%)
    interest_coverage: Mapped[Optional[float]] = mapped_column(Float)  # 이자보상배율

    # 시장 데이터
    market_cap: Mapped[Optional[float]] = mapped_column(Float)                  # 시가총액 (억원)
    foreign_shareholding_pct: Mapped[Optional[float]] = mapped_column(Float)   # 외국인 보유비율 (%)
    net_institutional_buying: Mapped[Optional[float]] = mapped_column(Float)   # 기관 순매수 (주)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # relationships
    stock: Mapped["Stock"] = relationship(back_populates="financial_metrics")  # noqa: F821
