"""SupervisorAgent 공유 상태."""

from __future__ import annotations

from typing import Optional
from typing_extensions import TypedDict, Annotated
import operator


class SupervisorState(TypedDict):
    # 실행 메타
    date: str                          # YYYY-MM-DD
    hitl_mode: str                     # FULL-AUTO / SEMI-AUTO / FULL-REVIEW
    report_type: str                   # full_analysis / daily_brief / ...

    # 종목 목록
    watchlist: list[str]               # stock_code 목록

    # 수집 완료 플래그
    collection_done: bool

    # 종목별 결과 누적 (aggregate_node에서 채워짐)
    stock_results: Annotated[list[dict], operator.add]
    failed_stocks: Annotated[list[str], operator.add]

    # 비교 보고서 (report_type="comparison" 전용)
    comparison_draft: Optional[str]

    # 최종 승인
    final_approved: bool
