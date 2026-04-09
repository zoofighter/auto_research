"""
analyze_node — RAG 수집 + 주가 이상 감지 + LLM 분석 메모 생성.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from langchain_ollama import OllamaLLM

import config
from agents.state.stock_state import StockState
from db.base import SessionLocal
from db.models.stock import Stock
from db.models.price import StockPrice
from db.models.dart import DartDisclosure
from db.models.news import NewsArticle
from vector_db.retriever import search

_llm = None


def _get_llm() -> OllamaLLM:
    global _llm
    if _llm is None:
        _llm = OllamaLLM(base_url=config.OLLAMA_BASE_URL, model=config.OLLAMA_MODEL)
    return _llm


def _build_price_context(stock_id: int) -> str:
    """최근 20거래일 OHLCV에서 ±3% 이상 변동일을 감지하고 공시·뉴스와 매핑한다."""
    session = SessionLocal()
    try:
        prices = (
            session.query(StockPrice)
            .filter_by(stock_id=stock_id)
            .order_by(StockPrice.trade_date.desc())
            .limit(21)
            .all()
        )
        if len(prices) < 2:
            return ""

        prices = list(reversed(prices))  # 오래된 순
        lines = []
        for i in range(1, len(prices)):
            prev_close = prices[i - 1].close
            curr = prices[i]
            if prev_close == 0:
                continue
            chg_pct = (curr.close - prev_close) / prev_close * 100
            if abs(chg_pct) < 3.0:
                continue

            sign = "급등" if chg_pct > 0 else "급락"
            line = f"{curr.trade_date}: {chg_pct:+.1f}% {sign}"

            # ±2일 내 공시 조회
            start_dt = curr.trade_date - timedelta(days=2)
            end_dt = curr.trade_date + timedelta(days=2)
            disclosures = (
                session.query(DartDisclosure)
                .filter(
                    DartDisclosure.stock_id == stock_id,
                    DartDisclosure.rcept_dt >= start_dt,
                    DartDisclosure.rcept_dt <= end_dt,
                )
                .all()
            )
            for d in disclosures:
                line += f" / 공시: {d.title} ({d.rcept_dt})"

            # ±2일 내 주요 뉴스
            start_dt_dt = f"{start_dt} 00:00:00"
            end_dt_dt = f"{end_dt} 23:59:59"
            news_list = (
                session.query(NewsArticle)
                .filter(
                    NewsArticle.stock_id == stock_id,
                    NewsArticle.published_at >= start_dt_dt,
                    NewsArticle.published_at <= end_dt_dt,
                    NewsArticle.relevance_score >= 0.7,
                )
                .all()
            )
            for n in news_list:
                line += f" / 뉴스: {n.headline}"

            lines.append(line)

        return "\n".join(lines) if lines else ""
    finally:
        session.close()


def analyze_node(state: StockState) -> dict:
    """RAG 수집 + 주가 이상 감지 + LLM 분석 메모 생성."""
    stock_code = state["stock_code"]
    company_name = state["company_name"]
    stock_id = state["stock_id"]
    _t0 = time.time()
    print(f"[analyze] 시작 — {company_name}({stock_code})")

    # RAG 검색 — 다각도 쿼리로 리포트 활용 극대화
    # 액면분할(2025-11) 이후 리포트만 사용 — 이전 목표주가는 현 주가와 단위 불일치
    from vector_db.retriever import search_by_text, ANALYST_REPORT_MIN_DATE
    queries = [
        f"{company_name} 목표주가 투자의견",
        f"{company_name} 실적 매출 영업이익",
        f"{company_name} 리스크 위험 우려",
        f"{company_name} 사업전망 성장동력",
    ]
    docs = search_by_text(queries, stock_id=stock_id, min_report_date=ANALYST_REPORT_MIN_DATE)

    # 주가 이상 감지
    price_ctx = _build_price_context(stock_id)

    # DB session으로 analysis_sessions INSERT
    session = SessionLocal()
    try:
        from db.models.analysis import AnalysisSession
        sess_rec = AnalysisSession(stock_id=stock_id, status="running")
        session.add(sess_rec)
        session.commit()
        session_id = sess_rec.id
    finally:
        session.close()

    # LLM 분석 메모 — 애널리스트 리포트 우선, 최대 12개 문서, 각 600자
    docs_sorted = sorted(docs, key=lambda x: (
        0 if x["source_type"] == "analyst_report" else 1,
        -x.get("score", 0)
    ))
    doc_texts = "\n\n".join(
        f"[{d['source_type']}] {d['content'][:600]}"
        for d in docs_sorted[:12]
    )
    prompt = (
        f"종목: {company_name}({stock_code})\n\n"
        f"[수집 문서 요약]\n{doc_texts}\n\n"
        f"[주가 이상 이벤트]\n{price_ctx or '없음'}\n\n"
        f"위 정보를 바탕으로 다음 항목을 간결하게 분석하라:\n"
        f"1. 투자의견 변화 추이\n"
        f"2. 핵심 리스크 요인\n"
        f"3. 주가 이상 원인 추정 (이벤트 있는 경우)\n"
        f"4. 추가 확인이 필요한 불확실 사항"
    )

    print(f"[analyze] RAG {len(docs)}건 수집, LLM 분석 메모 생성 중... ({time.time()-_t0:.1f}s)")
    _t1 = time.time()
    try:
        llm = _get_llm()
        analysis_notes = llm.invoke(prompt)
    except Exception as e:
        analysis_notes = f"[LLM 오류: {e}] 기본 분석 불가"
    print(f"[analyze] 완료 — 이상 이벤트 {len([l for l in price_ctx.splitlines() if l])}건 ({time.time()-_t1:.1f}s / 누적 {time.time()-_t0:.1f}s)")

    return {
        "session_id": session_id,
        "collected_docs": docs,
        "price_context": price_ctx,
        "analysis_notes": analysis_notes,
    }
