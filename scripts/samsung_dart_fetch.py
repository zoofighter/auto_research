"""
삼성전자 DART 공시 1년치 수집 + 실적 관련 공시 조회 스크립트.

실행:
    python3 scripts/samsung_dart_fetch.py           # 수집 + 조회
    python3 scripts/samsung_dart_fetch.py --view    # 조회만 (재수집 없음)
"""

import sys
import time
import io
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from bs4 import BeautifulSoup

import config
from db.base import init_db, SessionLocal
from db.models.stock import Stock
from db.models.dart import DartDisclosure

DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DART_DOC_URL  = "https://opendart.fss.or.kr/api/document.xml"
SUMMARY_MAX_LEN = 2000  # 실적 데이터는 더 길게

# 실적 관련 키워드
EARNINGS_KEYWORDS = [
    "영업(잠정)실적", "잠정실적", "영업실적", "사업보고서", "분기보고서",
    "반기보고서", "기업설명회", "IR개최", "실적발표",
]

STOCK_CODE = "005930"
CORP_CODE  = "00126380"  # 삼성전자 DART corp_code (6자리 아닌 8자리)


def _fetch_summary(rcept_no: str) -> Optional[str]:
    try:
        resp = requests.get(
            DART_DOC_URL,
            params={"crtfc_key": config.DART_API_KEY, "rcept_no": rcept_no},
            timeout=20,
        )
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            candidates = [f for f in zf.namelist() if f.lower().endswith((".htm", ".html", ".xml"))]
            if not candidates:
                return None
            main_file = max(candidates, key=lambda f: zf.getinfo(f).file_size)
            raw = zf.read(main_file)
            for enc in ("utf-8", "euc-kr", "cp949"):
                try:
                    html = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                return None
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        summary = "\n".join(lines)
        return summary[:SUMMARY_MAX_LEN] if summary else None
    except Exception as e:
        print(f"    [본문 실패] {rcept_no}: {e}")
        return None


def fetch_one_year(session, stock: Stock):
    """삼성전자 1년치 DART 공시 수집."""
    end_date   = date.today()
    start_date = end_date - timedelta(days=365)

    params = {
        "crtfc_key": config.DART_API_KEY,
        "corp_code": CORP_CODE,
        "bgn_de": start_date.strftime("%Y%m%d"),
        "end_de": end_date.strftime("%Y%m%d"),
        "page_count": 100,
    }

    inserted = 0
    page = 1
    while True:
        params["page_no"] = page
        try:
            resp = requests.get(DART_LIST_URL, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  [오류] page {page}: {e}")
            break

        if data.get("status") != "000":
            print(f"  [API] {data.get('message')}")
            break

        items = data.get("list", [])
        if not items:
            break

        for item in items:
            rcept_no = item.get("rcept_no", "")
            if not rcept_no:
                continue
            existing = session.query(DartDisclosure).filter_by(rcept_no=rcept_no).first()
            if existing:
                continue

            title    = item.get("report_nm", "")
            rcept_dt = date(
                int(item["rcept_dt"][:4]),
                int(item["rcept_dt"][4:6]),
                int(item["rcept_dt"][6:]),
            )

            print(f"  [{rcept_dt}] {title[:50]}")
            summary = _fetch_summary(rcept_no)
            time.sleep(0.3)

            record = DartDisclosure(
                stock_id=stock.id,
                rcept_no=rcept_no,
                disclosure_type="major_event",
                title=title,
                corp_name=item.get("corp_name", stock.company_name),
                rcept_dt=rcept_dt,
                url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
                is_major_event=any(kw in title for kw in EARNINGS_KEYWORDS),
                summary=summary,
            )
            session.add(record)
            inserted += 1

        session.commit()
        print(f"  [page {page}] {len(items)}건 처리, 누적 신규 {inserted}건")

        total_page = data.get("total_page", 1)
        if page >= total_page:
            break
        page += 1
        time.sleep(0.5)

    print(f"\n수집 완료: {inserted}건 신규 삽입")
    return inserted


def view_earnings(session, stock: Stock):
    """실적 관련 공시만 출력."""
    rows = (
        session.query(DartDisclosure)
        .filter_by(stock_id=stock.id)
        .order_by(DartDisclosure.rcept_dt.desc())
        .all()
    )

    earnings = [r for r in rows if any(kw in r.title for kw in EARNINGS_KEYWORDS)]
    print(f"\n{'='*60}")
    print(f"삼성전자 실적 관련 공시 ({len(earnings)}건)")
    print(f"{'='*60}\n")

    for r in earnings:
        print(f"[{r.rcept_dt}] {r.title}")
        print(f"  URL: {r.url}")
        if r.summary:
            print(f"  내용:\n")
            for line in r.summary.splitlines()[:30]:
                print(f"    {line}")
        print()


if __name__ == "__main__":
    init_db()
    session = SessionLocal()
    try:
        stock = session.query(Stock).filter_by(stock_code=STOCK_CODE).first()
        if not stock:
            print(f"종목 없음: {STOCK_CODE}")
            sys.exit(1)

        view_only = "--view" in sys.argv
        if not view_only:
            print(f"삼성전자 1년치 DART 공시 수집 시작...\n")
            fetch_one_year(session, stock)

        view_earnings(session, stock)
    finally:
        session.close()
