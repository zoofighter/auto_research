from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "stock_analysis.db"
DB_PATH.parent.mkdir(exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_session():
    """컨텍스트 매니저용 세션 팩토리."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """모든 테이블 생성 (개발/테스트용)."""
    from db.models import (  # noqa: F401
        stock, report, financial, dart, news, analysis, output, price, hitl
    )
    Base.metadata.create_all(bind=engine)
