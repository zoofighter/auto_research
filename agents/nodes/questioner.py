"""
question_node — 분석 메모 + 주가 이상 이벤트 기반 자율 질문 3~5개 생성.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from langchain_ollama import OllamaLLM
import config
from agents.state.stock_state import StockState

_llm = None


def _get_llm() -> OllamaLLM:
    global _llm
    if _llm is None:
        _llm = OllamaLLM(base_url=config.OLLAMA_BASE_URL, model=config.OLLAMA_MODEL)
    return _llm


def _parse_questions(text: str) -> list[str]:
    """LLM 출력에서 질문 목록을 파싱한다."""
    lines = text.strip().split("\n")
    questions = []
    for line in lines:
        line = re.sub(r"^[\d]+[.)]\s*", "", line).strip()
        if line and "?" in line or (line and len(line) > 10):
            questions.append(line)
    return questions[:5]


def question_node(state: StockState) -> dict:
    """분석 메모를 바탕으로 자율 질문 3~5개를 생성한다."""
    company_name = state["company_name"]
    stock_code = state["stock_code"]
    analysis_notes = state.get("analysis_notes", "")
    price_context = state.get("price_context", "")
    rewrite_guide = state.get("rewrite_guide")

    guide_section = ""
    if rewrite_guide:
        guide_section = f"\n[재작성 방향 가이드]\n{rewrite_guide}\n위 방향을 반드시 반영하여 질문을 생성하라.\n"

    prompt = (
        f"종목: {company_name}({stock_code})\n\n"
        f"[분석 메모]\n{analysis_notes[:600]}\n\n"
        f"[주가 이상 이벤트]\n{price_context or '없음'}\n"
        f"{guide_section}\n"
        f"위 분석에서 불확실하거나 추가 확인이 필요한 사항을 "
        f"웹 검색으로 확인할 수 있는 구체적인 질문 3~5개로 작성하라.\n"
        f"각 질문을 번호와 함께 한 줄씩 출력하라."
    )

    try:
        llm = _get_llm()
        raw = llm.invoke(prompt)
        questions = _parse_questions(raw)
        if not questions:
            questions = [f"{company_name} 최근 실적 전망은?",
                         f"{company_name} 주요 리스크 요인은?"]
    except Exception as e:
        questions = [f"{company_name} 최근 실적 전망은?",
                     f"{company_name} 주요 리스크 요인은?"]

    return {
        "generated_questions": questions,
        "rewrite_guide": None,  # 소비 완료
    }
