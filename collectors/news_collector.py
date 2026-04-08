from typing import Optional
"""
네이버 금융 종목 뉴스 수집기.
관심종목의 오늘 뉴스를 수집하고 Ollama(Qwen)로 관련도 점수를 산정한다.
Ollama 미설치 시 키워드 기반 폴백 점수를 사용한다.
"""

import re
import sys
import time
from datetime import datetime, date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.base import SessionLocal, init_db
from db.models.stock import Stock
from db.models.news import NewsArticle

NEWS_URL = "https://finance.naver.com/item/news_news.naver"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/",
}
STOCK_IMPACT_KEYWORDS = [
    "영업이익", "매출", "순이익", "실적", "목표주가", "투자의견", "상향", "하향",
    "인수", "합병", "분할", "유상증자", "자사주", "배당", "수주", "계약",
    "제재", "소송", "리콜", "특허",
]
MAX_NEWS_PER_STOCK = 20
TOP_NEWS_PER_STOCK = 5


def _fetch_news_list(stock_code: str, page: int = 1) -> list[dict]:
    """네이버 금융 종목 뉴스 목록 페이지를 파싱한다."""
    params = {"code": stock_code, "page": page}
    resp = requests.get(NEWS_URL, headers=HEADERS, params=params, timeout=10)
    resp.raise_for_status()
    resp.encoding = "euc-kr"
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    for row in soup.select("table.type5 tr"):
        title_tag = row.select_one("td.title a")
        info_tag = row.select_one("td.info")
        date_tag = row.select_one("td.date")
        if not title_tag:
            continue
        items.append({
            "headline": title_tag.get_text(strip=True),
            "url": "https://finance.naver.com" + title_tag["href"],
            "source": info_tag.get_text(strip=True) if info_tag else None,
            "published_at": _parse_datetime(date_tag.get_text(strip=True) if date_tag else ""),
        })
    return items


def _parse_datetime(text: str) -> Optional[datetime]:
    """'YYYY.MM.DD HH:MM' 또는 'YYYY.MM.DD' 형식 파싱."""
    text = text.strip()
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _is_recent(dt: Optional[datetime], days: int = 3) -> bool:
    """최근 N일 이내 뉴스 여부 (기본 3일)."""
    if dt is None:
        return False
    from datetime import timedelta
    return dt.date() >= date.today() - timedelta(days=days)


def _keyword_score(headline: str) -> float:
    """주가 영향 키워드 기반 관련도 점수 (폴백용)."""
    hits = sum(1 for kw in STOCK_IMPACT_KEYWORDS if kw in headline)
    return min(hits * 0.15, 0.9)


def _llm_score(headline: str, company_name: str) -> float:
    """Ollama(Qwen)로 관련도 점수 산정. 실패 시 키워드 폴백."""
    try:
        import config as _cfg
        payload = {
            "model": _cfg.OLLAMA_MODEL,
            "prompt": (
                f"다음 뉴스 제목이 '{company_name}' 주가에 미치는 영향도를 "
                f"0.0~1.0 사이의 숫자 하나만 출력하라. 다른 텍스트는 절대 출력하지 말 것.\n"
                f"뉴스: {headline}"
            ),
            "stream": False,
        }
        resp = requests.post(
            "http://localhost:11434/api/generate", json=payload, timeout=15
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
        match = re.search(r"[0-9]+\.?[0-9]*", raw)
        if match:
            score = float(match.group())
            return min(max(score, 0.0), 1.0)
    except Exception:
        pass
    return _keyword_score(headline)


def collect(use_llm: bool = True) -> list[dict]:
    """
    관심종목(is_watchlist=True)의 오늘 뉴스를 수집하여 news_articles 테이블에 적재.

    Args:
        use_llm: True면 Ollama로 관련도 점수 산정, False면 키워드 폴백

    Returns:
        삽입된 레코드 정보 목록
    """
    init_db()
    session = SessionLocal()
    inserted = []

    try:
        watchlist = session.query(Stock).filter_by(is_watchlist=True).all()
        if not watchlist:
            print("[news_collector] 관심종목 없음")
            return []

        for stock in watchlist:
            candidates = []
            for page in range(1, 4):
                items = _fetch_news_list(stock.stock_code, page)
                if not items:
                    break
                recent_items = [it for it in items if _is_recent(it["published_at"])]
                candidates.extend(recent_items)
                if len(candidates) >= MAX_NEWS_PER_STOCK:
                    break
                if not recent_items:
                    break
                time.sleep(0.5)

            # 관련도 점수 산정
            for item in candidates:
                if use_llm:
                    item["relevance_score"] = _llm_score(item["headline"], stock.company_name)
                else:
                    item["relevance_score"] = _keyword_score(item["headline"])

            # 상위 TOP_NEWS_PER_STOCK 건만 저장
            top = sorted(candidates, key=lambda x: x["relevance_score"], reverse=True)
            top = [it for it in top if it["relevance_score"] >= 0.5][:TOP_NEWS_PER_STOCK]

            for item in top:
                existing = session.query(NewsArticle).filter_by(url=item["url"]).first()
                if existing:
                    continue

                record = NewsArticle(
                    stock_id=stock.id,
                    headline=item["headline"],
                    url=item["url"],
                    source=item["source"],
                    published_at=item["published_at"],
                    relevance_score=item["relevance_score"],
                )
                session.add(record)
                session.flush()
                inserted.append({
                    "id": record.id,
                    "stock": stock.stock_code,
                    "headline": item["headline"],
                    "score": item["relevance_score"],
                })

            print(f"  [news_collector] {stock.stock_code} {stock.company_name}: "
                  f"수집 {len(candidates)}건 → 저장 {len(top)}건")
            time.sleep(1.0)

        session.commit()
        print(f"[news_collector] 총 삽입 {len(inserted)}건")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return inserted


if __name__ == "__main__":
    collect(use_llm=True)
