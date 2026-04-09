"""
네이버 금융 애널리스트 리포트 수집기.
기존 naver_research_downloader.py를 래핑하여 SQLite에 적재한다.
"""

import sys
import time
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.base import SessionLocal, init_db
from db.models.stock import Stock
from db.models.report import AnalystReport
from naver_research_downloader import fetch_report_list, download_pdf, safe_filename, is_today

SAVE_DIR = Path("/Users/boon/report")


def _parse_date(date_str: str) -> date:
    """'YY.MM.DD' 형식을 date 객체로 변환."""
    parts = date_str.split(".")
    year = 2000 + int(parts[0])
    return date(year, int(parts[1]), int(parts[2]))


def _get_or_create_stock(session, company_name: str) -> Stock:
    """company_name으로 stocks 테이블 조회, 없으면 INSERT."""
    stock = session.query(Stock).filter_by(company_name=company_name).first()
    if stock is None:
        stock = Stock(stock_code=f"UNKNOWN_{company_name[:8]}", company_name=company_name)
        session.add(stock)
        session.flush()
    return stock


def collect(today_only: bool = True, max_pages: int = 5, download: bool = True, start_page: int = 1) -> list[dict]:
    """
    리포트 목록을 수집하여 analyst_reports 테이블에 적재한다.

    Args:
        today_only:  True면 오늘 날짜 리포트만 수집
        max_pages:   마지막 페이지 번호
        download:    True면 PDF 파일도 로컬 저장
        start_page:  시작 페이지 번호 (기본 1)

    Returns:
        삽입된 레코드 정보 목록
    """
    init_db()
    session = SessionLocal()
    inserted = []

    try:
        seen_urls: set[str] = set()
        for page in range(start_page, max_pages + 1):
            reports = fetch_report_list(page)
            if not reports:
                break

            # 중복 페이지 감지: Naver가 동일 페이지를 반복 반환할 때 조기 종료
            page_urls = {r["pdf_url"] for r in reports}
            if page_urls.issubset(seen_urls):
                print(f"[naver_report] page {page}: 중복 페이지 감지, 수집 종료")
                break
            seen_urls.update(page_urls)

            page_has_target = False
            for r in reports:
                if today_only and not is_today(r["date"]):
                    continue
                page_has_target = True

                # 중복 체크
                existing = session.query(AnalystReport).filter_by(pdf_url=r["pdf_url"]).first()
                if existing:
                    continue

                stock = _get_or_create_stock(session, r["stock"])
                report_date = _parse_date(r["date"])

                pdf_path = None
                if download:
                    SAVE_DIR.mkdir(parents=True, exist_ok=True)
                    filename = safe_filename(
                        f"{r['date']}_{r['stock']}_{r['firm']}_{r['title'][:30]}.pdf"
                    )
                    save_path = SAVE_DIR / filename
                    if not save_path.exists():
                        success = download_pdf(r["pdf_url"], save_path)
                        if success:
                            pdf_path = str(save_path)
                        time.sleep(1.0)
                    else:
                        pdf_path = str(save_path)

                record = AnalystReport(
                    stock_id=stock.id,
                    title=r["title"],
                    firm_name=r["firm"],
                    report_date=report_date,
                    pdf_url=r["pdf_url"],
                    pdf_path=pdf_path,
                    is_processed=False,
                )
                session.add(record)
                session.flush()
                inserted.append({"id": record.id, "stock": r["stock"], "title": r["title"]})

            if today_only and not page_has_target:
                break
            time.sleep(1.5)

        session.commit()
        print(f"[naver_report] 삽입 {len(inserted)}건")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return inserted


if __name__ == "__main__":
    collect(today_only=False, start_page=151, max_pages=250)
