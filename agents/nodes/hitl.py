"""
HITL interrupt 노드 모음.
LangGraph interrupt()로 그래프를 일시 중단하고 사람 입력을 기다린다.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from langgraph.types import interrupt

import config
from agents.state.stock_state import StockState
from agents.notifier import notify_hitl1, notify_hitl2, notify_hitl4
from db.base import SessionLocal
from db.models.hitl import HitlFeedback


def _save_feedback(session_id: int, hitl_point: str, action: str,
                   original: str = None, revised: str = None,
                   feedback_text: str = None) -> None:
    """hitl_feedbacks 테이블에 응답 이력을 저장한다."""
    db = SessionLocal()
    try:
        rec = HitlFeedback(
            session_id=session_id,
            hitl_point=hitl_point,
            action=action,
            original_content=original,
            revised_content=revised,
            feedback_text=feedback_text,
            responded_at=datetime.now(timezone.utc),
        )
        db.add(rec)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


# ──────────────────────────────────────────────
# HITL-1: 질문 검토
# ──────────────────────────────────────────────
def hitl_q_node(state: StockState) -> dict:
    """HITL-1 — 질문 목록 검토. FULL-AUTO는 즉시 통과."""
    hitl_mode = state.get("hitl_mode", "SEMI-AUTO")
    questions = state.get("generated_questions", [])

    if hitl_mode == "FULL-AUTO":
        return {}

    # 알림 발송
    notify_hitl1(state["stock_code"], state["company_name"], questions)

    # interrupt — 그래프 일시 중단 (타임아웃은 외부 runner에서 처리)
    response = interrupt({
        "hitl_point": "HITL-1",
        "stock_code": state["stock_code"],
        "questions": questions,
    })

    # 응답 처리
    action = response.get("action", "timeout") if isinstance(response, dict) else "timeout"
    revised_questions = response.get("revised_questions", questions) if isinstance(response, dict) else questions

    _save_feedback(
        session_id=state.get("session_id", 0),
        hitl_point="HITL-1",
        action=action,
        original="\n".join(questions),
        revised="\n".join(revised_questions) if action in ("edit", "add") else None,
    )

    if action == "skip":
        return {"status": "skipped"}
    if action in ("edit", "add"):
        return {"generated_questions": revised_questions, "human_q_feedback": response}
    return {"human_q_feedback": response}  # approve / timeout


# ──────────────────────────────────────────────
# HITL-2: 초안 검토
# ──────────────────────────────────────────────
def hitl_draft_node(state: StockState) -> dict:
    """HITL-2 — 보고서 초안 검토. FULL-AUTO / SEMI-AUTO 모두 활성."""
    hitl_mode = state.get("hitl_mode", "SEMI-AUTO")
    report_draft = state.get("report_draft", "")

    if hitl_mode == "FULL-AUTO":
        return {}

    notify_hitl2(state["stock_code"], state["company_name"], report_draft)

    response = interrupt({
        "hitl_point": "HITL-2",
        "stock_code": state["stock_code"],
        "report_draft": report_draft[:500],
    })

    action = response.get("action", "timeout") if isinstance(response, dict) else "timeout"

    _save_feedback(
        session_id=state.get("session_id", 0),
        hitl_point="HITL-2",
        action=action,
        original=report_draft[:500],
        revised=response.get("revised_draft") if isinstance(response, dict) else None,
        feedback_text=response.get("guide") if isinstance(response, dict) else None,
    )

    if action == "edit" and isinstance(response, dict) and response.get("revised_draft"):
        return {"report_draft": response["revised_draft"], "human_draft_feedback": response}
    if action == "rewrite" and isinstance(response, dict):
        return {
            "rewrite_guide": response.get("guide", ""),
            "human_draft_feedback": response,
        }
    return {"human_draft_feedback": response}


# ──────────────────────────────────────────────
# HITL-4: 품질 미달 재작성 가이드
# ──────────────────────────────────────────────
def hitl_guide_node(state: StockState) -> dict:
    """HITL-4 — 품질 미달 시 재작성 방향 가이드 요청."""
    notify_hitl4(
        state["stock_code"],
        state["company_name"],
        state.get("quality_score", 0),
        state.get("iteration", 0),
    )

    response = interrupt({
        "hitl_point": "HITL-4",
        "stock_code": state["stock_code"],
        "quality_score": state.get("quality_score"),
    })

    action = response.get("action", "timeout") if isinstance(response, dict) else "timeout"

    _save_feedback(
        session_id=state.get("session_id", 0),
        hitl_point="HITL-4",
        action=action,
        feedback_text=response.get("guide") if isinstance(response, dict) else None,
    )

    if action == "force_approve":
        return {"force_approved": True}
    if action == "guide" and isinstance(response, dict):
        return {"rewrite_guide": response.get("guide", "")}
    return {"rewrite_guide": None}  # timeout → 가이드 없이 재시도
