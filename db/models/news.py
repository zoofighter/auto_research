from typing import Optional
from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.base import Base


class NewsArticle(Base):
    """관심종목 뉴스 (일 1회 수집)."""

    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    headline: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(100))         # 언론사
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    relevance_score: Mapped[Optional[float]] = mapped_column(Float)    # LLM 관련도 0.0~1.0
    summary: Mapped[Optional[str]] = mapped_column(Text)               # LLM 요약
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # relationships
    stock: Mapped["Stock"] = relationship(back_populates="news_articles")  # noqa: F821
