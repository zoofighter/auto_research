"""
/Users/boon/report/ 의 PDF 파일을 파싱하여 analyst_reports 테이블에 등록.
파일명 형식: YY.MM.DD_종목명_증권사_제목.pdf
"""

import sys
import re
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.base import init_db, SessionLocal
from db.models.stock import Stock
from db.models.report import AnalystReport

PDF_DIR = Path("/Users/boon/report")

# 수집 대상 종목명 필터 (빈 set이면 전체)
TARGET_STOCKS = {"삼성전자", "SK하이닉스"}


def _parse_filename(filename: str):
    """YY.MM.DD_종목명_증권사_제목.pdf 파싱."""
    stem = filename.replace(".pdf", "")
    parts = stem.split("_", 3)
    if len(parts) < 3:
        return None
    date_str = parts[0]   # 25.06.27
    stock_name = parts[1]
    firm_name = parts[2]
    title = parts[3] if len(parts) > 3 else stem

    try:
        p = date_str.split(".")
        report_date = date(2000 + int(p[0]), int(p[1]), int(p[2]))
    except Exception:
        return None

    return {
        "report_date": report_date,
        "stock_name": stock_name,
        "firm_name": firm_name,
        "title": title,
    }


def _get_or_create_stock(session, company_name: str) -> Stock:
    stock = session.query(Stock).filter_by(company_name=company_name).first()
    if stock is None:
        stock = Stock(stock_code=f"UNKNOWN_{company_name[:8]}", company_name=company_name)
        session.add(stock)
        session.flush()
    return stock


def migrate():
    init_db()
    session = SessionLocal()

    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    print(f"PDF 파일 수: {len(pdfs)}")

    inserted = 0
    skipped = 0
    failed = 0

    try:
        for pdf_path in pdfs:
            info = _parse_filename(pdf_path.name)
            if info is None:
                print(f"  [파싱실패] {pdf_path.name}")
                failed += 1
                continue

            # 종목 필터
            if TARGET_STOCKS and info["stock_name"] not in TARGET_STOCKS:
                skipped += 1
                continue

            # pdf_path 기준 중복 체크
            existing = session.query(AnalystReport).filter_by(pdf_path=str(pdf_path)).first()
            if existing:
                skipped += 1
                continue

            stock = _get_or_create_stock(session, info["stock_name"])

            record = AnalystReport(
                stock_id=stock.id,
                title=info["title"],
                firm_name=info["firm_name"],
                report_date=info["report_date"],
                pdf_url="",
                pdf_path=str(pdf_path),
                is_processed=False,
            )
            session.add(record)
            inserted += 1

            if inserted % 100 == 0:
                session.flush()
                print(f"  {inserted}건 처리 중...")

        session.commit()
        print(f"\n완료: 삽입 {inserted}건 / 스킵 {skipped}건 / 실패 {failed}건")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    migrate()
