from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.base import Base


class AnalysisSession(Base):
    """LangGraph 워크플로우 실행 세션."""

    __tablename__ = "analysis_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running / completed / failed
    iteration_count: Mapped[int] = mapped_column(Integer, default=0)
    generated_questions: Mapped[str | None] = mapped_column(Text)  # JSON 직렬화된 질문 리스트
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # relationships
    stock: Mapped["Stock"] = relationship(back_populates="analysis_sessions")  # noqa: F821
    web_search_results: Mapped[list["WebSearchResult"]] = relationship(back_populates="session")
    generated_reports: Mapped[list["GeneratedReport"]] = relationship(back_populates="session")  # noqa: F821


class WebSearchResult(Base):
    """자율 질문 기반 웹 검색 결과."""

    __tablename__ = "web_search_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("analysis_sessions.id"), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)     # 생성된 질문
    query: Mapped[str] = mapped_column(String(500), nullable=False) # 실제 검색어
    result_url: Mapped[str | None] = mapped_column(String(500))
    result_snippet: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # relationships
    session: Mapped["AnalysisSession"] = relationship(back_populates="web_search_results")
