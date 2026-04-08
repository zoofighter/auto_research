"""
DART Open API 공시 수집기.
API 키는 환경변수 DART_API_KEY 또는 config.py에서 읽는다.
"""

import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.base import SessionLocal, init_db
from db.models.stock import Stock
from db.models.dart import DartDisclosure

DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DART_CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"

MAJOR_EVENT_KEYWORDS = [
    "유상증자", "무상증자", "전환사채", "신주인수권", "주식매수선택권",
    "배당", "최대주주변경", "합병", "분할", "자기주식", "임원변경",
]


def _get_api_key() -> str:
    key = os.environ.get("DART_API_KEY", "")
    if not key:
        try:
            import config  # type: ignore
            key = getattr(config, "DART_API_KEY", "")
        except ImportError:
            pass
    if not key:
        raise ValueError("DART_API_KEY가 설정되지 않았습니다. 환경변수 또는 config.py에 설정하세요.")
    return key


def _is_major_event(title: str, disclosure_type: str) -> bool:
    if disclosure_type == "major_event":
        return True
    return any(kw in title for kw in MAJOR_EVENT_KEYWORDS)


def collect(days: int = 30) -> list[dict]:
    """
    관심종목(is_watchlist=True)의 DART 공시를 수집하여 dart_disclosures 테이블에 적재.

    Args:
        days: 최근 N일치 공시 수집

    Returns:
        삽입된 레코드 정보 목록
    """
    api_key = _get_api_key()
    init_db()
    session = SessionLocal()
    inserted = []

    try:
        watchlist = session.query(Stock).filter_by(is_watchlist=True).all()
        if not watchlist:
            print("[dart_api] 관심종목 없음")
            return []

        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        for stock in watchlist:
            params = {
                "crtfc_key": api_key,
                "corp_code": stock.stock_code,  # DART corp_code = stock_code로 우선 시도
                "bgn_de": start_date.strftime("%Y%m%d"),
                "end_de": end_date.strftime("%Y%m%d"),
                "page_count": 40,
            }
            try:
                resp = requests.get(DART_LIST_URL, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"  [dart_api] {stock.stock_code} 조회 실패: {e}")
                time.sleep(1.0)
                continue

            if data.get("status") != "000":
                print(f"  [dart_api] {stock.stock_code}: {data.get('message', 'API 오류')}")
                time.sleep(1.0)
                continue

            for item in data.get("list", []):
                rcept_no = item.get("rcept_no", "")
                if not rcept_no:
                    continue

                existing = session.query(DartDisclosure).filter_by(rcept_no=rcept_no).first()
                if existing:
                    continue

                title = item.get("report_nm", "")
                rcept_dt = date(
                    int(item["rcept_dt"][:4]),
                    int(item["rcept_dt"][4:6]),
                    int(item["rcept_dt"][6:]),
                )
                disclosure_type = _map_disclosure_type(item.get("form_nm", ""))

                record = DartDisclosure(
                    stock_id=stock.id,
                    rcept_no=rcept_no,
                    disclosure_type=disclosure_type,
                    title=title,
                    corp_name=item.get("corp_name", stock.company_name),
                    rcept_dt=rcept_dt,
                    url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
                    is_major_event=_is_major_event(title, disclosure_type),
                )
                session.add(record)
                session.flush()
                inserted.append({"id": record.id, "stock": stock.stock_code, "title": title})

            time.sleep(0.5)

        session.commit()
        print(f"[dart_api] 삽입 {len(inserted)}건")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return inserted


def _map_disclosure_type(form_nm: str) -> str:
    if "사업보고서" in form_nm:
        return "business_report"
    if "분기보고서" in form_nm or "반기보고서" in form_nm:
        return "quarterly"
    if "공정공시" in form_nm:
        return "fair_disclosure"
    return "major_event"


if __name__ == "__main__":
    collect(days=30)
