"""
HITL 알림 발송 — Telegram Bot / CLI 폴백.
Telegram token/chat_id는 환경변수로 주입.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def _send_telegram(text: str) -> bool:
    try:
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"[notifier] Telegram 실패: {e}")
        return False


def notify(message: str) -> None:
    """알림을 발송한다. 설정에 따라 Telegram 또는 CLI 출력."""
    method = config.HITL_NOTIFY_METHOD

    if method == "telegram" and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        if not _send_telegram(message):
            print(f"[HITL 알림] {message}")  # Telegram 실패 시 CLI 폴백
    else:
        print(f"\n{'='*60}")
        print(f"[HITL 알림]")
        print(message)
        print('='*60)


def notify_hitl1(stock_code: str, company_name: str, questions: list[str]) -> None:
    lines = [f"[HITL-1] {company_name}({stock_code}) 질문 검토 요청"]
    for i, q in enumerate(questions, 1):
        lines.append(f"  {i}. {q}")
    lines.append(f"\n응답: approve / edit <질문 수정> / skip")
    notify("\n".join(lines))


def notify_hitl2(stock_code: str, company_name: str, draft_summary: str) -> None:
    summary = draft_summary[:300] + "..." if len(draft_summary) > 300 else draft_summary
    msg = (
        f"[HITL-2] {company_name}({stock_code}) 초안 검토 요청\n\n"
        f"{summary}\n\n"
        f"응답: approve / edit <수정내용> / rewrite <방향 가이드>"
    )
    notify(msg)


def notify_hitl3(results: list[dict]) -> None:
    lines = ["[HITL-3] 전체 분석 완료 — 최종 승인 요청\n"]
    for r in results:
        status = r.get("status", "?")
        score = r.get("quality_score", 0)
        lines.append(f"  {r.get('stock_code')} {r.get('company_name','')}  [{status}]  score={score:.2f}")
    lines.append("\n응답: approve / reject")
    notify("\n".join(lines))


def notify_hitl4(stock_code: str, company_name: str, quality_score: float, iteration: int) -> None:
    msg = (
        f"[HITL-4] {company_name}({stock_code}) 품질 미달\n"
        f"  quality_score={quality_score:.2f}  iteration={iteration}\n\n"
        f"응답: guide <재작성 방향> / force_approve"
    )
    notify(msg)
