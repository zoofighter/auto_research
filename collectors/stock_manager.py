"""
종목 마스터 관리 CLI.

사용법:
  python collectors/stock_manager.py add 005930 삼성전자
  python collectors/stock_manager.py watchlist 005930
  python collectors/stock_manager.py remove 005930
  python collectors/stock_manager.py list
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.base import SessionLocal, init_db
from db.models.stock import Stock


def add_stock(stock_code: str, company_name: str, sector: str = None,
              market_cap_category: str = None, is_watchlist: bool = False) -> Stock:
    """종목을 stocks 테이블에 추가한다. 이미 있으면 company_name만 업데이트."""
    init_db()
    session = SessionLocal()
    try:
        stock = session.query(Stock).filter_by(stock_code=stock_code).first()
        if stock is None:
            stock = Stock(
                stock_code=stock_code,
                company_name=company_name,
                sector=sector,
                market_cap_category=market_cap_category,
                is_watchlist=is_watchlist,
            )
            session.add(stock)
            session.commit()
            session.refresh(stock)
            print(f"[stock_manager] 추가: {stock_code} {company_name}")
        else:
            stock.company_name = company_name
            if sector:
                stock.sector = sector
            session.commit()
            print(f"[stock_manager] 업데이트: {stock_code} {company_name}")
        return stock
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def set_watchlist(stock_code: str, flag: bool = True) -> bool:
    """관심종목 여부를 토글한다. 해당 종목이 없으면 False 반환."""
    session = SessionLocal()
    try:
        stock = session.query(Stock).filter_by(stock_code=stock_code).first()
        if stock is None:
            print(f"[stock_manager] 종목 없음: {stock_code}")
            return False
        stock.is_watchlist = flag
        session.commit()
        status = "관심종목 등록" if flag else "관심종목 해제"
        print(f"[stock_manager] {status}: {stock_code} {stock.company_name}")
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def list_stocks(watchlist_only: bool = False) -> list[dict]:
    """종목 목록을 반환한다."""
    session = SessionLocal()
    try:
        q = session.query(Stock)
        if watchlist_only:
            q = q.filter_by(is_watchlist=True)
        stocks = q.order_by(Stock.stock_code).all()
        result = [
            {
                "stock_code": s.stock_code,
                "company_name": s.company_name,
                "sector": s.sector,
                "is_watchlist": s.is_watchlist,
            }
            for s in stocks
        ]
        return result
    finally:
        session.close()


def get_watchlist() -> list[Stock]:
    """관심종목 ORM 객체 목록을 반환한다 (수집기 내부용)."""
    session = SessionLocal()
    try:
        return session.query(Stock).filter_by(is_watchlist=True).all()
    finally:
        session.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("사용법: stock_manager.py [add|watchlist|remove|list] ...")
        sys.exit(1)

    init_db()
    cmd = args[0]

    if cmd == "add" and len(args) >= 3:
        add_stock(args[1], args[2])
    elif cmd == "watchlist" and len(args) >= 2:
        set_watchlist(args[1], flag=True)
    elif cmd == "remove" and len(args) >= 2:
        set_watchlist(args[1], flag=False)
    elif cmd == "list":
        stocks = list_stocks()
        for s in stocks:
            wl = "★" if s["is_watchlist"] else " "
            print(f"  {wl} {s['stock_code']}  {s['company_name']}  {s['sector'] or ''}")
    else:
        print(f"알 수 없는 명령: {cmd}")
        sys.exit(1)
