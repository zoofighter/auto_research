"""
StockAnalysisAgent 서브그래프.
단일 종목 심층 분석 — 병렬 N개 동시 실행 (Supervisor의 Send() API).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from langgraph.graph import StateGraph, START, END

from agents.state.stock_state import StockState
from agents.nodes.analyst import analyze_node
from agents.nodes.questioner import question_node
from agents.nodes.searcher import search_node
from agents.nodes.synthesizer import synthesize_node
from agents.nodes.evaluator import evaluate_node, should_loop
from agents.nodes.hitl import hitl_q_node, hitl_draft_node, hitl_guide_node
from db.base import SessionLocal
from db.models.analysis import AnalysisSession
from reporters.markdown_writer import write_report


def complete_node(state: StockState) -> dict:
    """분석 완료 처리 — DB 업데이트 후 결과 반환."""
    session_id = state.get("session_id")
    db = SessionLocal()
    try:
        if session_id:
            rec = db.query(AnalysisSession).filter_by(id=session_id).first()
            if rec:
                from datetime import datetime
                rec.status = state.get("status", "completed")
                rec.completed_at = datetime.utcnow()
                rec.iteration_count = state.get("iteration", 0)
                import json
                rec.generated_questions = json.dumps(
                    state.get("generated_questions", []), ensure_ascii=False
                )
                db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

    # 보고서 파일 저장
    draft = state.get("report_draft", "")
    if draft:
        try:
            path = write_report(
                result={
                    "stock_code": state.get("stock_code", "unknown"),
                    "report_draft": draft,
                },
                report_type=state.get("report_type", "daily_brief"),
            )
            print(f"[complete_node] 보고서 저장: {path}")
        except Exception as e:
            print(f"[complete_node] 보고서 저장 실패: {e}")

    return {
        "status": state.get("status", "completed"),
    }


def _route_after_hitl_q(state: StockState) -> str:
    """HITL-1 후 라우팅: skip → complete, 나머지 → search."""
    if state.get("status") == "skipped":
        return "complete"
    return "search"


def _route_after_hitl_draft(state: StockState) -> str:
    """HITL-2 후 라우팅: rewrite → question, 나머지 → evaluate."""
    if state.get("rewrite_guide"):
        return "question"
    return "evaluate"


def build_stock_agent() -> StateGraph:
    g = StateGraph(StockState)

    g.add_node("analyze", analyze_node)
    g.add_node("question", question_node)
    g.add_node("hitl_q", hitl_q_node)
    g.add_node("search", search_node)
    g.add_node("synthesize", synthesize_node)
    g.add_node("hitl_draft", hitl_draft_node)
    g.add_node("evaluate", evaluate_node)
    g.add_node("hitl_guide", hitl_guide_node)
    g.add_node("complete", complete_node)

    g.add_edge(START, "analyze")
    g.add_edge("analyze", "question")
    g.add_edge("question", "hitl_q")
    g.add_conditional_edges("hitl_q", _route_after_hitl_q, {
        "search": "search",
        "complete": "complete",
    })
    g.add_edge("search", "synthesize")
    g.add_edge("synthesize", "hitl_draft")
    g.add_conditional_edges("hitl_draft", _route_after_hitl_draft, {
        "question": "question",
        "evaluate": "evaluate",
    })
    g.add_conditional_edges("evaluate", should_loop, {
        "complete": "complete",
        "hitl_guide": "hitl_guide",
        "question": "question",
    })
    g.add_conditional_edges("hitl_guide", lambda s: "complete" if s.get("force_approved") else "question", {
        "question": "question",
        "complete": "complete",
    })
    g.add_edge("complete", END)

    return g.compile()


stock_agent = build_stock_agent()
