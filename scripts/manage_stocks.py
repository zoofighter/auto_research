"""
종목 관리 CLI — watchlist 추가/삭제/조회/검색.

사용법:
  python3 scripts/manage_stocks.py list              # watchlist 조회
  python3 scripts/manage_stocks.py list --all        # 전체 종목 조회
  python3 scripts/manage_stocks.py add 005380 현대차  # 종목 추가 + watchlist 등록
  python3 scripts/manage_stocks.py add 005380        # 이미 DB에 있으면 이름 생략 가능
  python3 scripts/manage_stocks.py remove 005380     # watchlist 해제
  python3 scripts/manage_stocks.py delete 005380     # DB에서 완전 삭제
  python3 scripts/manage_stocks.py search 현대        # 회사명 검색
  python3 scripts/manage_stocks.py info 005380        # 종목 상세 정보
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config  # noqa: F401 — DB 경로 초기화
from db.base import SessionLocal, init_db
from db.models.stock import Stock
from sqlalchemy import text


def _get_session():
    return SessionLocal()


def cmd_list(args):
    """watchlist(또는 전체) 종목 출력."""
    s = _get_session()
    try:
        q = s.query(Stock)
        if not args.all:
            q = q.filter_by(is_watchlist=True)
        stocks = q.order_by(Stock.stock_code).all()

        if not stocks:
            print("등록된 종목이 없습니다.")
            return

        label = "전체 종목" if args.all else "Watchlist"
        print(f"\n{'='*55}")
        print(f"  {label} ({len(stocks)}개)")
        print(f"{'='*55}")
        print(f"  {'종목코드':<10} {'회사명':<20} {'watchlist'}")
        print(f"  {'-'*50}")
        for st in stocks:
            wl = "✓" if st.is_watchlist else ""
            print(f"  {st.stock_code:<10} {st.company_name:<20} {wl}")
        print(f"{'='*55}\n")
    finally:
        s.close()


def cmd_add(args):
    """종목 추가 또는 watchlist 등록."""
    stock_code = args.stock_code.strip()
    company_name = args.company_name.strip() if args.company_name else None

    s = _get_session()
    try:
        existing = s.query(Stock).filter_by(stock_code=stock_code).first()
        if existing:
            if existing.is_watchlist:
                print(f"[{stock_code}] {existing.company_name} — 이미 watchlist에 있습니다.")
                return
            existing.is_watchlist = True
            if company_name and existing.company_name != company_name:
                print(f"  회사명 업데이트: {existing.company_name} → {company_name}")
                existing.company_name = company_name
            s.commit()
            print(f"✓ [{stock_code}] {existing.company_name} — watchlist 등록 완료")
        else:
            if not company_name:
                print(f"오류: 신규 종목은 회사명이 필요합니다.")
                print(f"  예) python3 scripts/manage_stocks.py add {stock_code} 회사명")
                return
            new_stock = Stock(
                stock_code=stock_code,
                company_name=company_name,
                is_watchlist=True,
            )
            s.add(new_stock)
            s.commit()
            print(f"✓ [{stock_code}] {company_name} — 신규 등록 + watchlist 추가")
            print(f"  ※ 주가/공시 데이터는 별도 수집이 필요합니다:")
            print(f"     python3 collectors/price_collector.py {stock_code}")
            print(f"     python3 collectors/dart_api.py {stock_code}")
    finally:
        s.close()


def cmd_remove(args):
    """watchlist 해제 (DB 레코드는 유지)."""
    stock_code = args.stock_code.strip()
    s = _get_session()
    try:
        stock = s.query(Stock).filter_by(stock_code=stock_code).first()
        if not stock:
            print(f"오류: [{stock_code}] 종목을 찾을 수 없습니다.")
            return
        if not stock.is_watchlist:
            print(f"[{stock_code}] {stock.company_name} — 이미 watchlist에 없습니다.")
            return
        stock.is_watchlist = False
        s.commit()
        print(f"✓ [{stock_code}] {stock.company_name} — watchlist 해제 (데이터는 유지됨)")
    finally:
        s.close()


def cmd_delete(args):
    """DB에서 종목 완전 삭제 (관련 데이터 포함)."""
    stock_code = args.stock_code.strip()
    s = _get_session()
    try:
        stock = s.query(Stock).filter_by(stock_code=stock_code).first()
        if not stock:
            print(f"오류: [{stock_code}] 종목을 찾을 수 없습니다.")
            return

        # 관련 데이터 건수 확인
        counts = {}
        for table in ["analyst_reports", "dart_disclosures", "stock_prices", "news_articles"]:
            try:
                cnt = s.execute(text(f"SELECT COUNT(*) FROM {table} WHERE stock_id=:id"), {"id": stock.id}).scalar()
                if cnt:
                    counts[table] = cnt
            except Exception:
                pass

        if counts:
            print(f"\n[{stock_code}] {stock.company_name} 삭제 시 함께 삭제되는 데이터:")
            for table, cnt in counts.items():
                print(f"  - {table}: {cnt}건")
            confirm = input("\n정말 삭제하시겠습니까? (yes/no): ").strip().lower()
            if confirm != "yes":
                print("취소되었습니다.")
                return

        s.delete(stock)
        s.commit()
        print(f"✓ [{stock_code}] {stock.company_name} — 삭제 완료")
    finally:
        s.close()


def cmd_search(args):
    """회사명으로 종목 검색."""
    keyword = args.keyword.strip()
    s = _get_session()
    try:
        stocks = s.query(Stock).filter(Stock.company_name.like(f"%{keyword}%")).all()
        if not stocks:
            print(f"'{keyword}' 검색 결과 없음")
            return
        print(f"\n'{keyword}' 검색 결과 ({len(stocks)}개):")
        print(f"  {'종목코드':<12} {'회사명':<22} {'watchlist'}")
        print(f"  {'-'*45}")
        for st in stocks:
            wl = "✓" if st.is_watchlist else ""
            print(f"  {st.stock_code:<12} {st.company_name:<22} {wl}")
        print()
    finally:
        s.close()


def cmd_info(args):
    """종목 상세 정보 출력."""
    stock_code = args.stock_code.strip()
    s = _get_session()
    try:
        stock = s.query(Stock).filter_by(stock_code=stock_code).first()
        if not stock:
            print(f"오류: [{stock_code}] 종목을 찾을 수 없습니다.")
            return

        print(f"\n{'='*50}")
        print(f"  [{stock.stock_code}] {stock.company_name}")
        print(f"{'='*50}")
        print(f"  watchlist  : {'예' if stock.is_watchlist else '아니오'}")

        for table, label in [
            ("analyst_reports", "애널리스트 리포트"),
            ("dart_disclosures", "DART 공시"),
            ("stock_prices", "주가 데이터"),
            ("news_articles", "뉴스"),
        ]:
            try:
                cnt = s.execute(text(f"SELECT COUNT(*) FROM {table} WHERE stock_id=:id"), {"id": stock.id}).scalar()
                print(f"  {label:<18}: {cnt}건")
            except Exception:
                print(f"  {label:<18}: (테이블 없음)")

        # 최신 주가
        try:
            row = s.execute(
                text("SELECT trade_date, close FROM stock_prices WHERE stock_id=:id ORDER BY trade_date DESC LIMIT 1"),
                {"id": stock.id}
            ).fetchone()
            if row:
                print(f"  최신 종가        : {int(row[1]):,}원 ({row[0]})")
        except Exception:
            pass

        print(f"{'='*50}\n")
    finally:
        s.close()


def main():
    init_db()

    parser = argparse.ArgumentParser(
        description="종목 관리 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd")

    # list
    p_list = sub.add_parser("list", help="종목 목록 조회")
    p_list.add_argument("--all", action="store_true", help="watchlist 외 전체 종목 표시")

    # add
    p_add = sub.add_parser("add", help="종목 추가 / watchlist 등록")
    p_add.add_argument("stock_code", help="종목코드 (예: 005380)")
    p_add.add_argument("company_name", nargs="?", help="회사명 (신규 등록 시 필수)")

    # remove
    p_rm = sub.add_parser("remove", help="watchlist 해제")
    p_rm.add_argument("stock_code")

    # delete
    p_del = sub.add_parser("delete", help="종목 완전 삭제")
    p_del.add_argument("stock_code")

    # search
    p_search = sub.add_parser("search", help="회사명 검색")
    p_search.add_argument("keyword")

    # info
    p_info = sub.add_parser("info", help="종목 상세 정보")
    p_info.add_argument("stock_code")

    args = parser.parse_args()

    if args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "add":
        cmd_add(args)
    elif args.cmd == "remove":
        cmd_remove(args)
    elif args.cmd == "delete":
        cmd_delete(args)
    elif args.cmd == "search":
        cmd_search(args)
    elif args.cmd == "info":
        cmd_info(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
