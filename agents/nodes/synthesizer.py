"""
synthesize_node — 수집 문서 전체를 통합하여 report_type별 보고서 초안 생성.
"""

from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from langchain_ollama import OllamaLLM
import config
from agents.state.stock_state import StockState
from db.base import SessionLocal
from db.models.price import StockPrice

_llm = None

_ANALYST_SYSTEM = (
    "당신은 15년 경력의 한국 증권사 선임 애널리스트입니다. "
    "제공된 데이터를 근거로 사실에 기반한 전문적인 보고서를 작성합니다. "
    "추측이나 근거 없는 주장은 하지 않으며, 수치가 없으면 '데이터 미확인'으로 표기합니다. "
    "보고서는 글머리 기호(bullet point) 없이 완전한 문장으로 된 서술형 산문체로 작성합니다. "
    "각 섹션은 2~4개의 단락으로 구성하며, 수치와 근거를 문장 안에 자연스럽게 녹여 씁니다. "
    "보고서 작성 기준일: {today}\n\n"
)

TEMPLATES = {
    "full_analysis": (
        _ANALYST_SYSTEM
        + "{company_name}({stock_code}) 기업 심층 분석 보고서를 Markdown으로 작성하라.\n\n"
        "## Executive Summary\n투자의견, 목표주가, 핵심 투자포인트 3줄 요약\n\n"
        "## 재무 분석\n최근 실적 수치(매출·영업이익·순이익), YoY/QoQ 증감률, 마진 변화\n\n"
        "## 애널리스트 컨센서스\n증권사별 투자의견·목표주가 요약 및 방향성\n\n"
        "## 리스크 요인\n단기·중기 리스크를 구체적 수치와 함께 서술\n\n"
        "## 결론 및 투자 포인트\n매수/중립/매도 의견과 근거, 주요 모니터링 지표\n\n"
        "[데이터]\n{context}"
    ),
    "daily_brief": (
        _ANALYST_SYSTEM
        + "{company_name}({stock_code}) 일일 브리프를 Markdown으로 작성하라.\n\n"
        "## 오늘의 핵심 (3줄)\n주가 등락률과 원인, 가장 중요한 이벤트 1건, 내일 주목 포인트\n\n"
        "## 주요 이벤트\n공시·뉴스·리포트 중 주가 영향 상위 3건, 각각 영향도(긍정/부정/중립) 명시\n\n"
        "## 수급 동향\n거래량 특이사항, 외국인·기관 동향 (데이터 있을 경우)\n\n"
        "## 액션 포인트\n단기 투자자·장기 투자자별 대응 방향\n\n"
        "[데이터]\n{context}"
    ),
    "risk_focus": (
        _ANALYST_SYSTEM
        + "{company_name}({stock_code}) 리스크 집중 분석을 Markdown으로 작성하라.\n\n"
        "## 단기 리스크 (1~3개월)\n구체적 이벤트·일정과 영향 규모 추정\n\n"
        "## 중기 리스크 (3~12개월)\n업황·경쟁·규제 리스크\n\n"
        "## 장기 리스크 (1년 이상)\n구조적 리스크 및 대응 역량 평가\n\n"
        "## 리스크 종합 등급\n상/중상/중/중하/하 등급과 근거\n\n"
        "[데이터]\n{context}"
    ),
    "earnings": (
        _ANALYST_SYSTEM
        + "{company_name}({stock_code}) 실적 분석 보고서를 Markdown으로 작성하라.\n\n"
        "## 실적 요약\n매출·영업이익·순이익 실제치, 컨센서스 대비 서프라이즈 여부\n\n"
        "## 사업부문별 분석\n부문별 실적 기여도와 YoY 변화\n\n"
        "## 가이던스 및 전망\n회사 가이던스 또는 애널리스트 전망치 변화\n\n"
        "## 시장 반응 및 밸류에이션\n실적 발표 전후 주가 반응, PER·PBR 수준\n\n"
        "## 투자 의견\n실적 기반 투자의견 및 다음 분기 모니터링 포인트\n\n"
        "[데이터]\n{context}"
    ),
    "event_brief": (
        _ANALYST_SYSTEM
        + "{company_name}({stock_code}) 이벤트 긴급 분석을 Markdown으로 작성하라.\n\n"
        "## 이벤트 요약\n발생 일시, 내용, 공시 번호 (있을 경우)\n\n"
        "## 주가 영향 분석\n즉각 반응과 예상 지속 기간, 영향 규모 추정\n\n"
        "## 유사 선례\n과거 동일 유형 이벤트 발생 시 주가 패턴\n\n"
        "## 대응 방안\n투자자 포지션별 권고 행동\n\n"
        "[데이터]\n{context}"
    ),
    "price_report": (
        _ANALYST_SYSTEM
        + "{company_name}({stock_code}) 주가 분석 보고서를 Markdown으로 작성하라.\n"
        "반드시 제공된 OHLCV 수치를 직접 인용하여 작성하라. 수치가 없으면 '데이터 미확인'으로 표기하라.\n\n"
        "## 1. 현재 주가 현황\n"
        "최신 종가(원), 전일 대비 등락률(%), 거래량(주), 52주 고점·저점 대비 위치\n\n"
        "## 2. 단기 가격 흐름 (최근 5거래일)\n"
        "OHLC 테이블 (날짜·시가·고가·저가·종가·거래량), 방향성 판단\n\n"
        "## 3. 중기 가격 흐름 (최근 20거래일)\n"
        "기간 고점·저점·평균 종가, 추세 방향 (상승/횡보/하락)\n\n"
        "## 4. 주요 가격 이벤트\n"
        "±3% 이상 급등락 일자, 등락률, 연관 공시·뉴스 원인 분석\n\n"
        "## 5. 수급 분석\n"
        "거래량 급증 시점과 공시·뉴스 연관성, 평균 거래량 대비 배율\n\n"
        "## 6. 기술적 시사점\n"
        "주요 지지·저항 가격대, 이동평균 대비 위치, 추세 판단\n\n"
        "## 7. 투자 의견\n"
        "단기(1개월)·중기(3개월) 방향성 전망, 핵심 모니터링 지표\n\n"
        "[데이터]\n{context}"
    ),
}


def _get_llm() -> OllamaLLM:
    global _llm
    if _llm is None:
        _llm = OllamaLLM(base_url=config.OLLAMA_BASE_URL, model=config.OLLAMA_MODEL)
    return _llm


def _build_ohlcv_context(stock_id: int) -> str:
    """최근 20거래일 OHLCV 수치를 텍스트로 반환."""
    session = SessionLocal()
    try:
        prices = (
            session.query(StockPrice)
            .filter_by(stock_id=stock_id)
            .order_by(StockPrice.trade_date.desc())
            .limit(20)
            .all()
        )
        if not prices:
            return ""
        prices = list(reversed(prices))
        lines = ["날짜 | 시가 | 고가 | 저가 | 종가 | 거래량"]
        for p in prices:
            lines.append(
                f"{p.trade_date} | {int(p.open):,} | {int(p.high):,} | "
                f"{int(p.low):,} | {int(p.close):,} | {int(p.volume):,}"
            )
        return "\n".join(lines)
    finally:
        session.close()


def synthesize_node(state: StockState) -> dict:
    """수집 문서 + 분석 메모 + 검색 결과를 통합하여 보고서 초안을 생성한다."""
    company_name = state["company_name"]
    stock_code = state["stock_code"]
    stock_id = state.get("stock_id")
    report_type = state.get("report_type", "full_analysis")
    analysis_notes = state.get("analysis_notes", "")
    price_context = state.get("price_context", "")
    collected_docs = state.get("collected_docs", [])

    # 주가 보고서일 때 실제 OHLCV 수치 주입
    ohlcv_text = ""
    if report_type == "price_report" and stock_id:
        ohlcv_text = _build_ohlcv_context(stock_id)

    _t0 = time.time()
    print(f"[synthesize] 보고서 초안 작성 중... (report_type={report_type}, docs={len(collected_docs)}건)")
    today_str = date.today().isoformat()  # e.g. 2026-04-09

    # 컨텍스트 조합 — 애널리스트 리포트 우선 정렬, 최대 15개, 각 500자
    docs_sorted = sorted(
        collected_docs,
        key=lambda x: (0 if x.get("source_type") == "analyst_report" else 1, -x.get("score", 0))
    )

    def _doc_header(d: dict) -> str:
        meta = d.get("metadata", {})
        parts = [d.get("source_type", "unknown")]
        report_date = meta.get("report_date") or meta.get("date")
        firm = meta.get("firm_name") or meta.get("firm")
        if report_date:
            parts.append(f"날짜:{report_date}")
        if firm:
            parts.append(f"증권사:{firm}")
        return ", ".join(parts)

    doc_texts = "\n\n".join(
        f"[{_doc_header(d)}]\n{d['content'][:500]}"
        for d in docs_sorted[:15]
    )
    context = (
        f"[기준일: {today_str}]\n\n"
        f"[분석 메모]\n{analysis_notes[:500]}\n\n"
        f"[주가 이상 이벤트]\n{price_context or '없음'}\n\n"
        + (f"[최근 20거래일 OHLCV]\n{ohlcv_text}\n\n" if ohlcv_text else "")
        + f"[수집 문서]\n{doc_texts}"
    )

    template = TEMPLATES.get(report_type, TEMPLATES["full_analysis"])
    prompt = template.format(
        company_name=company_name,
        stock_code=stock_code,
        context=context,
        today=today_str,
    )

    try:
        llm = _get_llm()
        report_draft = llm.invoke(prompt)
    except Exception as e:
        report_draft = f"## {company_name} 분석 보고서\n\n[초안 생성 오류: {e}]"
    print(f"[synthesize] 완료 — {len(report_draft)}자 ({time.time()-_t0:.1f}s)")

    return {"report_draft": report_draft}
