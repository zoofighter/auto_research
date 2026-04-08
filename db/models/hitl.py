from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.base import Base


class HitlFeedback(Base):
    """HITL 피드백 이력 — 각 개입 지점의 사람 응답 저장."""

    __tablename__ = "hitl_feedbacks"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_sessions.id"), nullable=False, index=True
    )
    hitl_point: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # HITL-1 / HITL-2 / HITL-3 / HITL-4
    action: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # approved / edited / rewrite / skipped / force_approved / rejected / timeout
    original_content: Mapped[Optional[str]] = mapped_column(Text)   # 개입 전 내용
    revised_content: Mapped[Optional[str]] = mapped_column(Text)    # 사람이 수정한 내용
    feedback_text: Mapped[Optional[str]] = mapped_column(Text)      # 재작성 가이드 or 거절 사유
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    response_latency_min: Mapped[Optional[int]] = mapped_column(Integer)  # 응답까지 걸린 분
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    session: Mapped["AnalysisSession"] = relationship(back_populates="hitl_feedbacks")  # noqa: F821
