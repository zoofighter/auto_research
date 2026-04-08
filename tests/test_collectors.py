"""
Phase 2 수집기 테스트.
네트워크·Ollama 없이 실행 가능한 단위 테스트 위주로 구성한다.
실제 수집 테스트(integration)는 --integration 플래그 필요.
"""

import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.base import init_db, SessionLocal
from db.models.stock import Stock
from db.models.report import AnalystReport
from db.models.financial import FinancialMetric
from db.models.news import NewsArticle
from db.models.price import StockPrice


# ──────────────────────────────────────────────
# 공통 픽스처: 인메모리 DB
# ──────────────────────────────────────────────
def _setup_in_memory_db():
    """테스트용 인메모리 SQLite DB 초기화."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from db.base import Base
    import db.models  # noqa: F401 — 모든 모델 등록

    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return engine, Session


# ──────────────────────────────────────────────
# stock_manager 테스트
# ──────────────────────────────────────────────
class TestStockManager(unittest.TestCase):

    def setUp(self):
        self.engine, self.Session = _setup_in_memory_db()

    def _make_session(self):
        return self.Session()

    def test_add_stock(self):
        """종목 추가 후 DB에서 조회 가능해야 한다."""
        session = self._make_session()
        stock = Stock(stock_code="005930", company_name="삼성전자", is_watchlist=True)
        session.add(stock)
        session.commit()

        result = session.query(Stock).filter_by(stock_code="005930").first()
        self.assertIsNotNone(result)
        self.assertEqual(result.company_name, "삼성전자")
        self.assertTrue(result.is_watchlist)
        session.close()

    def test_watchlist_filter(self):
        """is_watchlist=True인 종목만 필터링되어야 한다."""
        session = self._make_session()
        session.add(Stock(stock_code="005930", company_name="삼성전자", is_watchlist=True))
        session.add(Stock(stock_code="000660", company_name="SK하이닉스", is_watchlist=False))
        session.commit()

        watchlist = session.query(Stock).filter_by(is_watchlist=True).all()
        self.assertEqual(len(watchlist), 1)
        self.assertEqual(watchlist[0].stock_code, "005930")
        session.close()

    def test_duplicate_stock_code(self):
        """동일 stock_code 중복 삽입 시 UniqueConstraint 위반."""
        from sqlalchemy.exc import IntegrityError
        session = self._make_session()
        session.add(Stock(stock_code="005930", company_name="삼성전자"))
        session.commit()

        session2 = self._make_session()
        session2.add(Stock(stock_code="005930", company_name="삼성전자(중복)"))
        with self.assertRaises(IntegrityError):
            session2.commit()
        session2.rollback()
        session2.close()
        session.close()


# ──────────────────────────────────────────────
# naver_report 테스트
# ──────────────────────────────────────────────
class TestNaverReport(unittest.TestCase):

    def test_parse_date(self):
        """'YY.MM.DD' → date 변환이 정확해야 한다."""
        from collectors.naver_report import _parse_date
        result = _parse_date("26.04.08")
        self.assertEqual(result, date(2026, 4, 8))

    def test_is_today(self):
        """오늘 날짜 포맷 확인."""
        from naver_research_downloader import is_today
        today_str = date.today().strftime("%y.%m.%d")
        self.assertTrue(is_today(today_str))
        self.assertFalse(is_today("20.01.01"))

    def test_safe_filename(self):
        """파일명에 사용 불가 문자가 제거되어야 한다."""
        from naver_research_downloader import safe_filename
        result = safe_filename("삼성전자/반도체<>리포트:2026")
        self.assertNotIn("/", result)
        self.assertNotIn("<", result)
        self.assertNotIn(">", result)
        self.assertNotIn(":", result)

    @patch("collectors.naver_report.fetch_report_list")
    @patch("collectors.naver_report.download_pdf", return_value=False)
    @patch("collectors.naver_report.SessionLocal")
    @patch("collectors.naver_report.init_db")
    def test_collect_inserts_record(self, mock_init, mock_session_cls,
                                    mock_download, mock_fetch):
        """fetch_report_list 결과가 DB에 삽입되어야 한다."""
        today_str = date.today().strftime("%y.%m.%d")
        mock_fetch.return_value = [{
            "stock": "삼성전자", "title": "테스트 리포트", "firm": "삼성증권",
            "date": today_str, "pdf_url": "https://example.com/test.pdf",
        }]

        # 인메모리 DB 세션 주입
        _, Session = _setup_in_memory_db()
        session = Session()
        mock_session_cls.return_value = session

        # _get_or_create_stock이 사용하는 Stock 사전 삽입
        stock = Stock(stock_code="005930", company_name="삼성전자")
        session.add(stock)
        session.commit()

        from collectors.naver_report import collect
        result = collect(today_only=True, max_pages=1, download=False)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["stock"], "삼성전자")
        session.close()


# ──────────────────────────────────────────────
# price_collector 테스트
# ──────────────────────────────────────────────
class TestPriceCollector(unittest.TestCase):

    def test_stock_price_model(self):
        """StockPrice 레코드가 정상적으로 저장되어야 한다."""
        _, Session = _setup_in_memory_db()
        session = Session()

        stock = Stock(stock_code="005930", company_name="삼성전자", is_watchlist=True)
        session.add(stock)
        session.flush()

        price = StockPrice(
            stock_id=stock.id,
            trade_date=date(2026, 4, 1),
            open=72000, high=73500, low=71800, close=73000, volume=15000000,
        )
        session.add(price)
        session.commit()

        result = session.query(StockPrice).filter_by(stock_id=stock.id).first()
        self.assertEqual(result.close, 73000)
        self.assertEqual(result.volume, 15000000)
        session.close()

    def test_unique_constraint(self):
        """같은 종목·날짜 중복 삽입 시 UniqueConstraint 위반."""
        from sqlalchemy.exc import IntegrityError
        _, Session = _setup_in_memory_db()
        session = Session()

        stock = Stock(stock_code="005930", company_name="삼성전자")
        session.add(stock)
        session.flush()

        p1 = StockPrice(stock_id=stock.id, trade_date=date(2026, 4, 1),
                        open=72000, high=73500, low=71800, close=73000, volume=10000)
        p2 = StockPrice(stock_id=stock.id, trade_date=date(2026, 4, 1),
                        open=72100, high=73600, low=71900, close=73100, volume=10001)
        session.add(p1)
        session.flush()
        session.add(p2)
        with self.assertRaises(IntegrityError):
            session.flush()
        session.close()

    @patch("collectors.price_collector.fdr.DataReader")
    @patch("collectors.price_collector.SessionLocal")
    @patch("collectors.price_collector.init_db")
    def test_collect_saves_prices(self, mock_init, mock_session_cls, mock_fdr):
        """DataReader 결과가 stock_prices 테이블에 삽입되어야 한다."""
        import pandas as pd

        _, Session = _setup_in_memory_db()
        session = Session()
        mock_session_cls.return_value = session

        stock = Stock(stock_code="005930", company_name="삼성전자", is_watchlist=True)
        session.add(stock)
        session.commit()
        stock_id = stock.id  # 세션 닫히기 전에 저장

        # FinanceDataReader 목 데이터
        mock_df = pd.DataFrame({
            "Open": [72000, 72500],
            "High": [73000, 73200],
            "Low": [71500, 72000],
            "Close": [72800, 73000],
            "Volume": [12000000, 11000000],
        }, index=pd.to_datetime(["2026-04-07", "2026-04-08"]))
        mock_fdr.return_value = mock_df

        from collectors.price_collector import collect
        collect(initial=False)

        prices = session.query(StockPrice).filter_by(stock_id=stock_id).all()
        self.assertEqual(len(prices), 2)
        self.assertEqual(prices[0].close, 72800)
        session.close()


# ──────────────────────────────────────────────
# news_collector 테스트
# ──────────────────────────────────────────────
class TestNewsCollector(unittest.TestCase):

    def test_keyword_score_high(self):
        """주요 키워드 포함 헤드라인은 높은 점수를 받아야 한다."""
        from collectors.news_collector import _keyword_score
        score = _keyword_score("삼성전자 영업이익 목표주가 상향 조정")
        self.assertGreater(score, 0.3)

    def test_keyword_score_low(self):
        """관련 없는 헤드라인은 낮은 점수를 받아야 한다."""
        from collectors.news_collector import _keyword_score
        score = _keyword_score("오늘 날씨 맑음")
        self.assertEqual(score, 0.0)

    def test_parse_datetime(self):
        """날짜 파싱이 정확해야 한다."""
        from collectors.news_collector import _parse_datetime
        dt = _parse_datetime("2026.04.08 14:30")
        self.assertEqual(dt, datetime(2026, 4, 8, 14, 30))

    def test_is_today(self):
        """오늘 날짜 판별이 정확해야 한다."""
        from collectors.news_collector import _is_today
        self.assertTrue(_is_today(datetime.combine(date.today(), datetime.min.time())))
        self.assertFalse(_is_today(datetime(2020, 1, 1)))

    @patch("collectors.news_collector._fetch_news_list")
    @patch("collectors.news_collector.SessionLocal")
    @patch("collectors.news_collector.init_db")
    def test_collect_saves_top_news(self, mock_init, mock_session_cls, mock_fetch):
        """관련도 상위 뉴스만 저장되어야 한다."""
        _, Session = _setup_in_memory_db()
        session = Session()
        mock_session_cls.return_value = session

        stock = Stock(stock_code="005930", company_name="삼성전자", is_watchlist=True)
        session.add(stock)
        session.commit()

        today = datetime.combine(date.today(), datetime.min.time())
        mock_fetch.return_value = [
            {"headline": f"삼성전자 영업이익 {i}분기 실적 목표주가 상향",
             "url": f"https://news.naver.com/{i}",
             "source": "한국경제",
             "published_at": today}
            for i in range(8)
        ]

        from collectors.news_collector import collect
        result = collect(use_llm=False)

        self.assertLessEqual(len(result), 5)  # TOP_NEWS_PER_STOCK = 5
        session.close()


# ──────────────────────────────────────────────
# naver_financial 테스트
# ──────────────────────────────────────────────
class TestNaverFinancial(unittest.TestCase):

    def test_parse_float(self):
        """다양한 숫자 포맷이 올바르게 파싱되어야 한다."""
        from collectors.naver_financial import _parse_float
        self.assertEqual(_parse_float("12.34"), 12.34)
        self.assertEqual(_parse_float("1,234.5"), 1234.5)
        self.assertEqual(_parse_float("15.2%"), 15.2)
        self.assertIsNone(_parse_float("N/A"))
        self.assertIsNone(_parse_float("-"))

    @patch("collectors.naver_financial._scrape_metrics")
    @patch("collectors.naver_financial.SessionLocal")
    @patch("collectors.naver_financial.init_db")
    def test_collect_inserts_metrics(self, mock_init, mock_session_cls, mock_scrape):
        """스크래핑 결과가 financial_metrics 테이블에 삽입되어야 한다."""
        _, Session = _setup_in_memory_db()
        session = Session()
        mock_session_cls.return_value = session

        stock = Stock(stock_code="005930", company_name="삼성전자", is_watchlist=True)
        session.add(stock)
        session.commit()

        mock_scrape.return_value = {"per": 12.5, "pbr": 1.3, "roe": 10.2, "market_cap": 430000.0}
        stock_id = stock.id  # 세션 닫히기 전에 저장

        from collectors.naver_financial import collect
        result = collect()

        self.assertEqual(len(result), 1)
        metric = session.query(FinancialMetric).filter_by(stock_id=stock_id).first()
        self.assertIsNotNone(metric)
        self.assertEqual(metric.per, 12.5)
        session.close()

    @patch("collectors.naver_financial._scrape_metrics")
    @patch("collectors.naver_financial.SessionLocal")
    @patch("collectors.naver_financial.init_db")
    def test_collect_skips_duplicate(self, mock_init, mock_session_cls, mock_scrape):
        """오늘 이미 수집된 종목은 스킵해야 한다."""
        _, Session = _setup_in_memory_db()
        session = Session()
        mock_session_cls.return_value = session

        stock = Stock(stock_code="005930", company_name="삼성전자", is_watchlist=True)
        session.add(stock)
        session.flush()

        # 오늘 데이터 사전 삽입
        session.add(FinancialMetric(
            stock_id=stock.id, metric_date=date.today(), per=10.0
        ))
        session.commit()

        from collectors.naver_financial import collect
        result = collect()

        self.assertEqual(len(result), 0)
        mock_scrape.assert_not_called()
        session.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
