"""
네이버 증권 리서치 - 기업분석 리포트 PDF 일괄 다운로드
대상: https://finance.naver.com/research/company_list.naver
"""

import time
import requests
from datetime import date
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup

BASE_URL = "https://finance.naver.com"
LIST_URL = "https://finance.naver.com/research/company_list.naver"
SAVE_DIR = Path("/Users/boon/report")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/research/",
}


def fetch_report_list(page: int = 1) -> list[dict]:
    """리스트 페이지에서 리포트 메타데이터 + PDF URL 추출"""
    params = {"page": page}
    res = requests.get(LIST_URL, headers=HEADERS, params=params, timeout=10)
    res.raise_for_status()
    res.encoding = "euc-kr"

    soup = BeautifulSoup(res.text, "html.parser")
    # tbody가 없으므로 > tbody > 제거
    rows = soup.select("table.type_1 tr")

    reports = []
    for row in rows:
        cols = row.select("td")
        if len(cols) < 5:
            continue

        # 실제 컬럼 순서: 종목명 | 제목 | 증권사 | 첨부(PDF) | 작성일 | 조회수
        stock_name  = cols[0].get_text(strip=True)
        title_tag   = cols[1].select_one("a")
        firm_name   = cols[2].get_text(strip=True)
        pdf_tag     = cols[3].select_one("a[href]")   # 첨부 컬럼
        report_date = cols[4].get_text(strip=True)    # 작성일

        if not title_tag or not pdf_tag:
            continue

        title   = title_tag.get_text(strip=True)
        pdf_url = pdf_tag["href"]

        reports.append({
            "stock":   stock_name,
            "title":   title,
            "firm":    firm_name,
            "date":    report_date,
            "pdf_url": pdf_url,
        })

    return reports



def is_today(report_date: str) -> bool:
    """날짜 문자열이 오늘인지 확인 (네이버 형식: 'YY.MM.DD', 예: 26.04.08)"""
    today = date.today()
    today_str = today.strftime("%y.%m.%d")   # 두 자리 연도
    return report_date == today_str


def download_pdf(pdf_url: str, save_path: Path) -> bool:
    """PDF 다운로드. 성공하면 True."""
    try:
        res = requests.get(pdf_url, headers=HEADERS, timeout=30, stream=True)
        res.raise_for_status()

        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "wb") as f:
            for chunk in res.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"  [다운로드 실패] {pdf_url} → {e}")
        return False


def safe_filename(text: str) -> str:
    """파일명에 사용할 수 없는 문자 제거"""
    keep = " .-_()[]"
    return "".join(c if (c.isalnum() or c in keep) else "_" for c in text).strip()


def run(today_only: bool = True, max_pages: int = 5):
    """
    메인 실행 함수

    Args:
        today_only: True면 오늘 날짜 리포트만 다운로드
        max_pages:  최대 페이지 수 (오늘 것만 받을 땐 보통 1~2페이지)
    """
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"저장 경로: {SAVE_DIR.resolve()}")

    downloaded = 0
    skipped    = 0
    seen_urls: set[str] = set()

    for page in range(1, max_pages + 1):
        print(f"\n[페이지 {page}] 목록 조회 중...")
        reports = fetch_report_list(page)

        if not reports:
            print("  → 리포트 없음, 중단")
            break

        # 중복 페이지 감지: Naver가 동일 페이지를 반복 반환하면 조기 종료
        page_urls = {r["pdf_url"] for r in reports}
        if page_urls.issubset(seen_urls):
            print(f"  → 중복 페이지 감지 (page {page}), 수집 종료")
            break
        seen_urls.update(page_urls)

        page_has_today = False
        for r in reports:
            if today_only and not is_today(r["date"]):
                skipped += 1
                continue

            page_has_today = True
            filename  = safe_filename(f"{r['date']}_{r['stock']}_{r['firm']}_{r['title'][:30]}.pdf")
            save_path = SAVE_DIR / filename

            if save_path.exists():
                print(f"  [스킵-중복] {filename}")
                skipped += 1
                continue

            print(f"  [다운로드] {r['stock']} | {r['firm']} | {r['date']}")
            success = download_pdf(r["pdf_url"], save_path)
            if success:
                print(f"    → 저장: {filename}")
                downloaded += 1

            time.sleep(1.0)  # 서버 부하 방지

        # 오늘 리포트만 받는 경우: 이 페이지에 오늘 것이 하나도 없으면 중단
        if today_only and not page_has_today:
            print("  → 오늘 리포트 없음, 이후 페이지 스킵")
            break

        time.sleep(1.5)

    print(f"\n완료: 다운로드 {downloaded}개 / 스킵 {skipped}개")


if __name__ == "__main__":
    run(today_only=False, max_pages=150)
