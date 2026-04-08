"""
보고서 Markdown 파일 생성 (Phase 5 스텁).
report_draft를 파일로 저장한다.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config


def write_report(result: dict, run_date: str = None, report_type: str = "full_analysis") -> str:
    """
    보고서 초안을 Markdown 파일로 저장한다.
    Returns: 저장된 파일 경로
    """
    run_date = run_date or str(date.today())
    stock_code = result.get("stock_code", "unknown")
    draft = result.get("draft", result.get("report_draft", ""))

    out_dir = config.REPORT_DIR / run_date
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{stock_code}_{report_type}.md"
    filepath = out_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(draft)

    print(f"[markdown_writer] 저장: {filepath}")
    return str(filepath)
