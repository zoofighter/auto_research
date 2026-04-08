"""
주가 OHLCV 시계열 수집기.
FinanceDataReader로 KRX 일별 주가를 수집하여 stock_prices 테이블에 적재한다.
"""

import sys
import warnings
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

warnings.filterwarnings("ignore")  # urllib3 OpenSSL 경고 억제

import FinanceDataReader as fdr  # noqa: E402

from db.base import SessionLocal, init_db  # noqa: E402
from db.models.stock import Stock  # noqa: E402
from db.models.price import StockPrice  # noqa: E402


def collect(initial: bool = False) -> list[dict]:
    """
    관심종목(is_watchlist=True)의 OHLCV를 수집하여 stock_prices 테이블에 UPSERT.

    Args:
        initial: True면 1년치 전체 수집, False면 마지막 수집일 이후만 수집

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
            print("[price_collector] 관심종목 없음")
            return []

        for stock in watchlist:
            # 마지막 수집일 조회
            last = (
                session.query(StockPrice.trade_date)
                .filter_by(stock_id=stock.id)
                .order_by(StockPrice.trade_date.desc())
                .first()
            )

            if initial or last is None:
                start = today - timedelta(days=365)
            else:
                start = last[0] + timedelta(days=1)

            if start > today:
                print(f"  [price_collector] {stock.stock_code} 최신 상태, 스킵")
                continue

            try:
                df = fdr.DataReader(stock.stock_code, start.strftime("%Y-%m-%d"))
            except Exception as e:
                print(f"  [price_collector] {stock.stock_code} 조회 실패: {e}")
                continue

            if df is None or df.empty:
                print(f"  [price_collector] {stock.stock_code} 데이터 없음")
                continue

            count = 0
            for idx, row in df.iterrows():
                price_date = idx.date() if hasattr(idx, "date") else idx

                existing = (
                    session.query(StockPrice)
                    .filter_by(stock_id=stock.id, trade_date=price_date)
                    .first()
                )
                if existing:
                    continue

                record = StockPrice(
                    stock_id=stock.id,
                    trade_date=price_date,
                    open=float(row.get("Open", row.get("open", 0))),
                    high=float(row.get("High", row.get("high", 0))),
                    low=float(row.get("Low", row.get("low", 0))),
                    close=float(row.get("Close", row.get("close", 0))),
                    volume=int(row.get("Volume", row.get("volume", 0))),
                )
                session.add(record)
                count += 1

            session.flush()
            inserted_count = count
            print(f"  [price_collector] {stock.stock_code} {stock.company_name}: {inserted_count}건 삽입")
            inserted.extend([{"stock": stock.stock_code, "count": inserted_count}])

        session.commit()
        total = sum(r["count"] for r in inserted)
        print(f"[price_collector] 총 {total}건 삽입")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return inserted


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--initial", action="store_true", help="1년치 전체 수집")
    args = parser.parse_args()
    collect(initial=args.initial)
