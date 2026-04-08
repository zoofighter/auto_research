"""
evaluate_node — 보고서 품질을 4개 항목으로 LLM 자체 평가.
quality_score < threshold 시 루프 재진입 또는 HITL-4.
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


def _parse_score(text: str, label: str) -> float:
    """'근거 충분성: 0.25' 형식에서 점수 파싱."""
    pattern = rf"{label}[:\s]+([0-9]+\.?[0-9]*)"
    m = re.search(pattern, text)
    if m:
        return min(float(m.group(1)), 0.3)
    return 0.1  # 파싱 실패 시 기본값


def evaluate_node(state: StockState) -> dict:
    """보고서 초안을 4개 항목으로 평가하여 quality_score를 산정한다."""
    report_draft = state.get("report_draft", "")
    iteration = state.get("iteration", 0)

    prompt = (
        f"다음 보고서를 4개 항목으로 평가하라. 각 항목은 최대 점수를 초과할 수 없다.\n\n"
        f"[보고서]\n{report_draft[:800]}\n\n"
        f"다음 형식으로 숫자만 출력하라:\n"
        f"근거 충분성: <0.0~0.3>\n"
        f"균형성: <0.0~0.3>\n"
        f"구체성: <0.0~0.2>\n"
        f"논리성: <0.0~0.2>"
    )

    try:
        llm = _get_llm()
        raw = llm.invoke(prompt)
        s1 = _parse_score(raw, "근거 충분성")
        s2 = _parse_score(raw, "균형성")
        s3 = _parse_score(raw, "구체성")
        s4 = _parse_score(raw, "논리성")
        quality_score = round(min(s1 + s2 + s3 + s4, 1.0), 3)
    except Exception:
        quality_score = 0.5  # LLM 실패 시 중간값

    return {
        "quality_score": quality_score,
        "iteration": iteration + 1,
    }


def should_loop(state: StockState) -> str:
    """
    평가 결과에 따른 라우팅:
      - 통과 (force_approved 포함) → "complete"
      - 최대 반복 도달 → "complete"
      - HITL-4 필요 (FULL-REVIEW) → "hitl_guide"
      - 재시도 가능 → "question"  (question_node 재진입)
    """
    score = state.get("quality_score", 0)
    iteration = state.get("iteration", 0)
    hitl_mode = state.get("hitl_mode", "SEMI-AUTO")
    force_approved = state.get("force_approved", False)

    if force_approved or score >= config.QUALITY_THRESHOLD:
        return "complete"
    if iteration >= config.MAX_ITERATIONS:
        return "complete"  # 강제 완료
    if hitl_mode == "FULL-REVIEW":
        return "hitl_guide"
    return "question"
