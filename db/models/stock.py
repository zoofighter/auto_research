from typing import Optional
from datetime import datetime
from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.base import Base


class Stock(Base):
    """종목 마스터 테이블."""

    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(100), nullable=False)
    sector: Mapped[Optional[str]] = mapped_column(String(100))
    market_cap_category: Mapped[Optional[str]] = mapped_column(String(20))  # KOSPI/KOSDAQ/KONEX
    is_watchlist: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # relationships
    analyst_reports: Mapped[list["AnalystReport"]] = relationship(back_populates="stock")  # noqa: F821
    analyst_opinions: Mapped[list["AnalystOpinion"]] = relationship(back_populates="stock")  # noqa: F821
    financial_metrics: Mapped[list["FinancialMetric"]] = relationship(back_populates="stock")  # noqa: F821
    dart_disclosures: Mapped[list["DartDisclosure"]] = relationship(back_populates="stock")  # noqa: F821
    news_articles: Mapped[list["NewsArticle"]] = relationship(back_populates="stock")  # noqa: F821
    analysis_sessions: Mapped[list["AnalysisSession"]] = relationship(back_populates="stock")  # noqa: F821
    generated_reports: Mapped[list["GeneratedReport"]] = relationship(back_populates="stock")  # noqa: F821
    stock_prices: Mapped[list["StockPrice"]] = relationship(back_populates="stock")  # noqa: F821
