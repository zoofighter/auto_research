"""
synthesize_node — 수집 문서 전체를 통합하여 report_type별 보고서 초안 생성.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from langchain_ollama import OllamaLLM
import config
from agents.state.stock_state import StockState

_llm = None

TEMPLATES = {
    "full_analysis": (
        "다음 데이터를 바탕으로 {company_name}({stock_code}) 심층 분석 보고서를 Markdown으로 작성하라.\n"
        "섹션: ## Executive Summary / ## 기업 개요 / ## 재무 분석 / "
        "## 애널리스트 컨센서스 / ## 리스크 요인 / ## 결론 및 투자 포인트 / ## 출처\n\n"
        "{context}"
    ),
    "daily_brief": (
        "다음 데이터를 바탕으로 {company_name}({stock_code}) 일일 브리프를 Markdown으로 작성하라.\n"
        "섹션: ## 오늘의 변화 요약(3줄) / ## 주요 이벤트 / ## 액션 포인트\n\n"
        "{context}"
    ),
    "risk_focus": (
        "다음 데이터를 바탕으로 {company_name}({stock_code}) 리스크 집중 분석을 Markdown으로 작성하라.\n"
        "섹션: ## 단기 리스크 / ## 중기 리스크 / ## 장기 리스크 / ## 리스크 종합 등급\n\n"
        "{context}"
    ),
    "earnings": (
        "다음 데이터를 바탕으로 {company_name}({stock_code}) 실적 시즌 분석을 Markdown으로 작성하라.\n"
        "섹션: ## 컨센서스 vs 실제 실적 / ## 가이던스 변화 / ## 시장 반응 / ## 전망\n\n"
        "{context}"
    ),
    "event_brief": (
        "다음 데이터를 바탕으로 {company_name}({stock_code}) 이벤트 긴급 분석을 Markdown으로 작성하라.\n"
        "섹션: ## 이벤트 요약 / ## 주가 영향 분석 / ## 유사 선례 / ## 대응 방안\n\n"
        "{context}"
    ),
}


def _get_llm() -> OllamaLLM:
    global _llm
    if _llm is None:
        _llm = OllamaLLM(base_url=config.OLLAMA_BASE_URL, model=config.OLLAMA_MODEL)
    return _llm


def synthesize_node(state: StockState) -> dict:
    """수집 문서 + 분석 메모 + 검색 결과를 통합하여 보고서 초안을 생성한다."""
    company_name = state["company_name"]
    stock_code = state["stock_code"]
    report_type = state.get("report_type", "full_analysis")
    analysis_notes = state.get("analysis_notes", "")
    price_context = state.get("price_context", "")
    collected_docs = state.get("collected_docs", [])

    # 컨텍스트 조합 (토큰 절약을 위해 각 소스 상위 3건)
    doc_texts = "\n\n".join(
        f"[{d['source_type']}] {d['content'][:300]}"
        for d in collected_docs[:8]
    )
    context = (
        f"[분석 메모]\n{analysis_notes[:500]}\n\n"
        f"[주가 이상 이벤트]\n{price_context or '없음'}\n\n"
        f"[수집 문서]\n{doc_texts}"
    )

    template = TEMPLATES.get(report_type, TEMPLATES["full_analysis"])
    prompt = template.format(
        company_name=company_name,
        stock_code=stock_code,
        context=context,
    )

    try:
        llm = _get_llm()
        report_draft = llm.invoke(prompt)
    except Exception as e:
        report_draft = f"## {company_name} 분석 보고서\n\n[초안 생성 오류: {e}]"

    return {"report_draft": report_draft}
