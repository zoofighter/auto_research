"""
search_node — 생성된 질문으로 웹 검색을 수행하고 결과를 DB + collected_docs에 저장.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from langchain_community.tools import DuckDuckGoSearchRun

from agents.state.stock_state import StockState
from db.base import SessionLocal
from db.models.analysis import WebSearchResult
from vector_db.retriever import search_by_text, ANALYST_REPORT_MIN_DATE

_search_tool = None


def _get_search_tool() -> DuckDuckGoSearchRun:
    global _search_tool
    if _search_tool is None:
        _search_tool = DuckDuckGoSearchRun()
    return _search_tool


def search_node(state: StockState) -> dict:
    """생성된 질문으로 RAG 재검색 + 웹 검색 후 결과를 DB 저장 + collected_docs 추가."""
    questions = state.get("generated_questions", [])
    session_id = state.get("session_id")
    company_name = state["company_name"]
    stock_id = state.get("stock_id")

    search_results = []
    new_docs = list(state.get("collected_docs", []))  # 기존 docs 유지
    db_session = SessionLocal()

    # ── 질문 기반 RAG 재검색 (애널리스트 리포트 추가 발굴) ──────
    if questions and stock_id:
        rag_docs = search_by_text(questions[:5], stock_id=stock_id, min_report_date=ANALYST_REPORT_MIN_DATE)
        existing_contents = {d["content"][:100] for d in new_docs}
        for d in rag_docs:
            if d["content"][:100] not in existing_contents:
                new_docs.append(d)
                existing_contents.add(d["content"][:100])

    try:
        tool = _get_search_tool()
        for question in questions[:5]:  # 질문당 1건 검색
            query = f"{company_name} {question}"
            try:
                snippet = tool.run(query)
                snippet = snippet[:800] if snippet else ""
            except Exception as e:
                snippet = f"[검색 실패: {e}]"

            result = {
                "question": question,
                "query": query,
                "snippet": snippet,
                "url": "",
            }
            search_results.append(result)

            # DB 저장
            if session_id:
                rec = WebSearchResult(
                    session_id=session_id,
                    question=question,
                    query=query,
                    result_snippet=snippet,
                )
                db_session.add(rec)

            # collected_docs 추가
            if snippet and not snippet.startswith("[검색 실패"):
                new_docs.append({
                    "content": f"[웹 검색: {question}]\n{snippet}",
                    "source_type": "web",
                    "source_id": 0,
                    "metadata": {"query": query},
                })

        db_session.commit()
    except Exception:
        db_session.rollback()
        raise
    finally:
        db_session.close()

    return {
        "search_results": search_results,
        "collected_docs": new_docs,
    }
