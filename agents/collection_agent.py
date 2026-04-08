"""
CollectionAgent 서브그래프.
Phase 2 수집기들을 LangGraph 노드로 래핑하여 순차 실행.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing_extensions import TypedDict

sys.path.insert(0, str(Path(__file__).parent.parent))

from langgraph.graph import StateGraph, START, END


class CollectionState(TypedDict):
    errors: list[str]
    naver_report_done: bool
    dart_done: bool
    financial_done: bool
    news_done: bool
    price_done: bool
    index_done: bool


# ── 노드 함수 ────────────────────────────────────────────────

def naver_report_node(state: CollectionState) -> dict:
    try:
        from collectors.naver_report import collect
        collect(today_only=True, max_pages=3, download=True)
        return {"naver_report_done": True}
    except Exception as e:
        return {"naver_report_done": False, "errors": [f"naver_report: {e}"]}


def dart_node(state: CollectionState) -> dict:
    try:
        from collectors.dart_api import collect
        collect(days=7)
        return {"dart_done": True}
    except Exception as e:
        return {"dart_done": False, "errors": [f"dart: {e}"]}


def financial_node(state: CollectionState) -> dict:
    try:
        from collectors.naver_financial import collect
        collect()
        return {"financial_done": True}
    except Exception as e:
        return {"financial_done": False, "errors": [f"financial: {e}"]}


def news_node(state: CollectionState) -> dict:
    try:
        from collectors.news_collector import collect
        collect(use_llm=True)
        return {"news_done": True}
    except Exception as e:
        return {"news_done": False, "errors": [f"news: {e}"]}


def price_node(state: CollectionState) -> dict:
    try:
        from collectors.price_collector import collect
        collect(initial=False)
        return {"price_done": True}
    except Exception as e:
        return {"price_done": False, "errors": [f"price: {e}"]}


def indexer_node(state: CollectionState) -> dict:
    try:
        from vector_db.indexer import run_all
        run_all()
        return {"index_done": True}
    except Exception as e:
        return {"index_done": False, "errors": [f"indexer: {e}"]}


# ── 그래프 빌드 ────────────────────────────────────────────────

def build_collection_agent() -> StateGraph:
    g = StateGraph(CollectionState)

    g.add_node("naver_report_node", naver_report_node)
    g.add_node("dart_node", dart_node)
    g.add_node("financial_node", financial_node)
    g.add_node("news_node", news_node)
    g.add_node("price_node", price_node)
    g.add_node("indexer_node", indexer_node)

    # 순차 실행 (개별 노드 실패 무관하게 계속 진행)
    g.add_edge(START, "naver_report_node")
    g.add_edge("naver_report_node", "dart_node")
    g.add_edge("dart_node", "financial_node")
    g.add_edge("financial_node", "news_node")
    g.add_edge("news_node", "price_node")
    g.add_edge("price_node", "indexer_node")
    g.add_edge("indexer_node", END)

    return g.compile()


collection_agent = build_collection_agent()
