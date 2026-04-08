from typing import Optional
"""
네이버 금융 재무지표 수집기.
종목 페이지에서 PER/PBR/ROE 등 핵심 지표를 스크래핑하여 financial_metrics 테이블에 적재.
"""

import sys
import time
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.base import SessionLocal, init_db
from db.models.stock import Stock
from db.models.financial import FinancialMetric

BASE_URL = "https://finance.naver.com/item/main.naver"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/",
}


def _parse_float(text: str) -> Optional[float]:
    """'12,345.67%' 형식의 텍스트를 float으로 변환."""
    cleaned = text.replace(",", "").replace("%", "").strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _scrape_metrics(stock_code: str) -> dict:
    """네이버 금융 종목 페이지에서 재무 지표를 스크래핑한다."""
    url = f"{BASE_URL}?code={stock_code}"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    resp.encoding = "euc-kr"
    soup = BeautifulSoup(resp.text, "html.parser")

    metrics = {}

    # 시가총액 (억원)
    cap_tag = soup.select_one("em#_market_sum")
    if cap_tag:
        # 예: "43,052억원" or "430조 5,200억"
        raw = cap_tag.get_text(strip=True).replace("조", "").replace("억원", "").replace(",", "")
        metrics["market_cap"] = _parse_float(raw)

    # 투자 지표 테이블 (per, pbr, roe 등)
    for tag in soup.select("table.per_table tr"):
        cols = tag.select("td")
        if len(cols) < 2:
            continue
        label = tag.select_one("th").get_text(strip=True) if tag.select_one("th") else ""
        val_text = cols[0].get_text(strip=True) if cols else ""
        if "PER" in label:
            metrics["per"] = _parse_float(val_text)
        elif "PBR" in label:
            metrics["pbr"] = _parse_float(val_text)
        elif "ROE" in label:
            metrics["roe"] = _parse_float(val_text)

    # 외국인 보유비율
    foreign_tag = soup.select_one("em#_foreign_ratio")
    if foreign_tag:
        metrics["foreign_shareholding_pct"] = _parse_float(foreign_tag.get_text(strip=True))

    return metrics


def collect() -> list[dict]:
    """
    관심종목(is_watchlist=True)의 오늘 재무지표를 수집하여 financial_metrics 테이블에 적재.

    Returns:
        삽입된 레코드 정보 목록
    """
    init_db()
    session = SessionLocal()
    inserted = []
    today = date.today()

    try:
        watchlist = session.query(Stock).filter_by(is_watchlist=True).all()
        if not watchlist:
            print("[naver_financial] 관심종목 없음")
            return []

        for stock in watchlist:
            # 오늘 이미 수집한 경우 스킵
            existing = (
                session.query(FinancialMetric)
                .filter_by(stock_id=stock.id, metric_date=today)
                .first()
            )
            if existing:
                print(f"  [naver_financial] {stock.stock_code} 오늘 이미 수집됨, 스킵")
                continue

            try:
                metrics = _scrape_metrics(stock.stock_code)
            except Exception as e:
                print(f"  [naver_financial] {stock.stock_code} 스크래핑 실패: {e}")
                time.sleep(2.0)
                continue

            record = FinancialMetric(
                stock_id=stock.id,
                metric_date=today,
                per=metrics.get("per"),
                pbr=metrics.get("pbr"),
                roe=metrics.get("roe"),
                market_cap=metrics.get("market_cap"),
                foreign_shareholding_pct=metrics.get("foreign_shareholding_pct"),
            )
            session.add(record)
            session.flush()
            inserted.append({
                "id": record.id,
                "stock": stock.stock_code,
                "per": record.per,
                "pbr": record.pbr,
            })
            print(f"  [naver_financial] {stock.stock_code} {stock.company_name} "
                  f"PER={record.per} PBR={record.pbr} ROE={record.roe}")
            time.sleep(1.5)

        session.commit()
        print(f"[naver_financial] 삽입 {len(inserted)}건")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return inserted


if __name__ == "__main__":
    collect()
