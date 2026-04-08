"""
SupervisorAgent — 최상위 오케스트레이터.
CollectionAgent → StockAgent×N(병렬) → OutputAgent → HITL-3
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send, interrupt

import config
from agents.state.supervisor_state import SupervisorState
from agents.state.stock_state import StockState
from agents.collection_agent import collection_agent
from agents.stock_agent import stock_agent
from agents.notifier import notify_hitl3
from db.base import SessionLocal
from db.models.stock import Stock


# ── 노드 함수 ────────────────────────────────────────────────

def init_node(state: SupervisorState) -> dict:
    """실행 날짜, HITL 모드, watchlist 초기화."""
    db = SessionLocal()
    try:
        stocks = db.query(Stock).filter_by(is_watchlist=True).all()
        watchlist = [s.stock_code for s in stocks]
    finally:
        db.close()

    return {
        "date": state.get("date", str(date.today())),
        "hitl_mode": state.get("hitl_mode", config.HITL_MODE),
        "report_type": state.get("report_type", config.DEFAULT_REPORT_TYPE),
        "watchlist": watchlist,
        "collection_done": False,
        "stock_results": [],
        "failed_stocks": [],
        "comparison_draft": None,
        "final_approved": False,
    }


def collection_node(state: SupervisorState) -> dict:
    """CollectionAgent 서브그래프 실행 (동기)."""
    try:
        collection_agent.invoke({"errors": [], "naver_report_done": False,
                                  "dart_done": False, "financial_done": False,
                                  "news_done": False, "price_done": False,
                                  "index_done": False})
        return {"collection_done": True}
    except Exception as e:
        print(f"[supervisor] collection 실패: {e}")
        return {"collection_done": True}  # 수집 실패해도 분석 진행


def dispatch_node(state: SupervisorState) -> list[Send]:
    """Send() API로 종목별 StockAgent를 병렬 디스패치."""
    db = SessionLocal()
    try:
        watchlist = state.get("watchlist", [])
        hitl_mode = state.get("hitl_mode", config.HITL_MODE)
        report_type = state.get("report_type", config.DEFAULT_REPORT_TYPE)

        sends = []
        for stock_code in watchlist[:config.MAX_WATCHLIST]:
            stock = db.query(Stock).filter_by(stock_code=stock_code).first()
            if stock is None:
                continue
            initial_state: StockState = {
                "stock_code": stock_code,
                "company_name": stock.company_name,
                "stock_id": stock.id,
                "session_id": None,
                "report_type": report_type,
                "collected_docs": [],
                "price_context": "",
                "analysis_notes": "",
                "generated_questions": [],
                "search_results": [],
                "report_draft": "",
                "quality_score": 0.0,
                "iteration": 0,
                "status": "running",
                "hitl_mode": hitl_mode,
                "human_q_feedback": None,
                "human_draft_feedback": None,
                "rewrite_guide": None,
                "force_approved": False,
            }
            sends.append(Send("stock_agent", initial_state))
        return sends
    finally:
        db.close()


def aggregate_node(state: SupervisorState) -> dict:
    """모든 StockAgent 결과 집계. comparison 시 비교 보고서 생성."""
    stock_results = state.get("stock_results", [])
    failed = [r["stock_code"] for r in stock_results if r.get("status") == "failed"]

    comparison_draft = None
    if state.get("report_type") == "comparison" and len(stock_results) > 1:
        try:
            from langchain_ollama import OllamaLLM
            from reporters.templates.comparison import PROMPT_TEMPLATE
            llm = OllamaLLM(base_url=config.OLLAMA_BASE_URL, model=config.OLLAMA_MODEL)
            context = "\n\n".join(
                f"[{r['stock_code']} {r.get('company_name','')}]\n{r.get('draft','')[:400]}"
                for r in stock_results if r.get("status") == "completed"
            )
            comparison_draft = llm.invoke(PROMPT_TEMPLATE.format(context=context))
        except Exception as e:
            print(f"[supervisor] comparison 보고서 생성 실패: {e}")

    return {
        "failed_stocks": failed,
        "comparison_draft": comparison_draft,
    }


def output_node(state: SupervisorState) -> dict:
    """OutputAgent: 완료 종목의 보고서 파일 생성."""
    stock_results = state.get("stock_results", [])
    report_type = state.get("report_type", "full_analysis")
    run_date = state.get("date", str(date.today()))

    for result in stock_results:
        if result.get("status") != "completed":
            continue
        try:
            from reporters.markdown_writer import write_report
            write_report(result, run_date, report_type)
        except Exception as e:
            print(f"[supervisor] 보고서 생성 실패 {result.get('stock_code')}: {e}")

    return {}


def hitl_final_node(state: SupervisorState) -> dict:
    """HITL-3 — 전체 최종 승인. FULL-AUTO는 즉시 통과."""
    hitl_mode = state.get("hitl_mode", "SEMI-AUTO")

    if hitl_mode == "FULL-AUTO":
        return {"final_approved": True}

    notify_hitl3(state.get("stock_results", []))

    response = interrupt({
        "hitl_point": "HITL-3",
        "stock_results": state.get("stock_results", []),
    })

    action = response.get("action", "timeout") if isinstance(response, dict) else "timeout"
    approved = action in ("approve", "timeout")

    return {"final_approved": approved}


# ── 그래프 빌드 ────────────────────────────────────────────────

def build_supervisor() -> StateGraph:
    g = StateGraph(SupervisorState)

    g.add_node("init", init_node)
    g.add_node("collection", collection_node)
    g.add_node("dispatch", dispatch_node)
    g.add_node("stock_agent", stock_agent)   # 서브그래프
    g.add_node("aggregate", aggregate_node)
    g.add_node("output", output_node)
    g.add_node("hitl_final", hitl_final_node)

    g.add_edge(START, "init")
    g.add_edge("init", "collection")
    g.add_edge("collection", "dispatch")
    g.add_edge("dispatch", "stock_agent")
    g.add_edge("stock_agent", "aggregate")
    g.add_edge("aggregate", "output")
    g.add_edge("output", "hitl_final")
    g.add_edge("hitl_final", END)

    return g.compile()


supervisor = build_supervisor()
