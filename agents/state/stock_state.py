"""StockAnalysisAgent 개별 종목 상태."""

from __future__ import annotations

from typing import Optional
from typing_extensions import TypedDict


class StockState(TypedDict):
    # 식별
    stock_code: str
    company_name: str
    stock_id: int                      # SQLite stocks.id
    session_id: Optional[int]          # analysis_sessions.id (analyze_node에서 생성)
    report_type: str                   # Supervisor에서 주입

    # 분석 데이터
    collected_docs: list[dict]         # RAG 수집 문서
    price_context: str                 # 주가 이상 감지 텍스트
    analysis_notes: str                # LLM 분석 메모
    generated_questions: list[str]     # 자율 생성 질문
    search_results: list[dict]         # 웹 검색 결과
    report_draft: str                  # 보고서 초안 (Markdown)

    # 제어
    quality_score: float               # 0.0~1.0
    iteration: int                     # 루프 카운터 (최대 3)
    status: str                        # running / completed / failed / skipped

    # HITL
    hitl_mode: str
    human_q_feedback: Optional[dict]   # HITL-1 응답
    human_draft_feedback: Optional[dict]  # HITL-2 응답
    rewrite_guide: Optional[str]       # HITL-4 재작성 방향
    force_approved: bool               # 품질 미달 강제 승인
