"""
SQLite → ChromaDB 색인 파이프라인.
is_processed=False 레코드를 청크 분할 후 ChromaDB에 upsert한다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from db.base import SessionLocal, init_db
from db.models.report import AnalystReport
from db.models.dart import DartDisclosure
from db.models.news import NewsArticle
from db.models.analysis import WebSearchResult
from vector_db.chroma_client import get_collection, get_embedding_function

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """OllamaEmbeddings로 텍스트 벡터화. 실패 시 예외 전파."""
    embed_fn = get_embedding_function()
    return embed_fn.embed_documents(texts)


def index_analyst_reports(session) -> int:
    """analyst_reports: PDF → 페이지 청크 → ChromaDB upsert."""
    collection = get_collection("analyst_reports")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    count = 0

    records = session.query(AnalystReport).filter_by(is_processed=False).all()
    for rec in records:
        try:
            if not rec.pdf_path or not Path(rec.pdf_path).exists():
                # PDF 없으면 title + firm_name으로 단일 청크
                doc_id = f"ar_{rec.id}_p0"
                text = f"{rec.title} - {rec.firm_name} ({rec.report_date})"
                embeddings = _embed_texts([text])
                collection.upsert(
                    ids=[doc_id],
                    documents=[text],
                    embeddings=embeddings,
                    metadatas=[{
                        "source_type": "analyst_report",
                        "source_id": rec.id,
                        "stock_code": str(rec.stock_id),
                        "firm_name": rec.firm_name,
                        "report_date": str(rec.report_date),
                    }],
                )
            else:
                loader = PyPDFLoader(rec.pdf_path)
                pages = loader.load()
                chunks = splitter.split_documents(pages)
                for i, chunk in enumerate(chunks):
                    doc_id = f"ar_{rec.id}_p{i}"
                    text = chunk.page_content
                    embeddings = _embed_texts([text])
                    collection.upsert(
                        ids=[doc_id],
                        documents=[text],
                        embeddings=embeddings,
                        metadatas=[{
                            "source_type": "analyst_report",
                            "source_id": rec.id,
                            "stock_code": str(rec.stock_id),
                            "firm_name": rec.firm_name,
                            "report_date": str(rec.report_date),
                            "page_num": i,
                        }],
                    )

            rec.is_processed = True
            count += 1
        except Exception as e:
            print(f"  [indexer] analyst_report {rec.id} 실패: {e}")

    session.commit()
    return count


def index_dart_disclosures(session) -> int:
    """dart_disclosures: summary 텍스트 → ChromaDB upsert."""
    collection = get_collection("dart_disclosures")
    count = 0

    records = (
        session.query(DartDisclosure)
        .filter(DartDisclosure.summary.isnot(None))
        .all()
    )
    existing_ids = set(collection.get(include=[])["ids"])

    for rec in records:
        doc_id = f"dart_{rec.id}"
        if doc_id in existing_ids:
            continue
        text = f"{rec.title}\n\n{rec.summary}"
        try:
            embeddings = _embed_texts([text])
            collection.upsert(
                ids=[doc_id],
                documents=[text],
                embeddings=embeddings,
                metadatas=[{
                    "source_type": "dart",
                    "source_id": rec.id,
                    "stock_code": str(rec.stock_id),
                    "rcept_dt": str(rec.rcept_dt),
                    "is_major_event": str(rec.is_major_event),
                }],
            )
            count += 1
        except Exception as e:
            print(f"  [indexer] dart {rec.id} 실패: {e}")

    return count


def index_news_articles(session) -> int:
    """news_articles: summary 텍스트 → ChromaDB upsert."""
    collection = get_collection("news_articles")
    count = 0

    records = (
        session.query(NewsArticle)
        .filter(NewsArticle.summary.isnot(None))
        .all()
    )
    existing_ids = set(collection.get(include=[])["ids"])

    for rec in records:
        doc_id = f"news_{rec.id}"
        if doc_id in existing_ids:
            continue
        text = f"{rec.headline}\n\n{rec.summary}"
        try:
            embeddings = _embed_texts([text])
            collection.upsert(
                ids=[doc_id],
                documents=[text],
                embeddings=embeddings,
                metadatas=[{
                    "source_type": "news",
                    "source_id": rec.id,
                    "stock_code": str(rec.stock_id),
                    "published_at": str(rec.published_at) if rec.published_at else "",
                    "relevance_score": str(rec.relevance_score or 0),
                }],
            )
            count += 1
        except Exception as e:
            print(f"  [indexer] news {rec.id} 실패: {e}")

    return count


def index_web_search_results(session) -> int:
    """web_search_results: snippet → ChromaDB upsert."""
    collection = get_collection("web_search_results")
    count = 0

    records = (
        session.query(WebSearchResult)
        .filter(WebSearchResult.result_snippet.isnot(None))
        .all()
    )
    existing_ids = set(collection.get(include=[])["ids"])

    for rec in records:
        doc_id = f"web_{rec.id}"
        if doc_id in existing_ids:
            continue
        text = f"{rec.question}\n\n{rec.result_snippet}"
        try:
            embeddings = _embed_texts([text])
            collection.upsert(
                ids=[doc_id],
                documents=[text],
                embeddings=embeddings,
                metadatas=[{
                    "source_type": "web",
                    "source_id": rec.id,
                    "session_id": str(rec.session_id),
                    "result_url": rec.result_url or "",
                }],
            )
            count += 1
        except Exception as e:
            print(f"  [indexer] web_search {rec.id} 실패: {e}")

    return count


def run_all() -> dict[str, int]:
    """전체 색인 파이프라인 실행. 결과 카운트 반환."""
    init_db()
    session = SessionLocal()
    results = {}
    try:
        results["analyst_reports"] = index_analyst_reports(session)
        results["dart_disclosures"] = index_dart_disclosures(session)
        results["news_articles"] = index_news_articles(session)
        results["web_search_results"] = index_web_search_results(session)
    finally:
        session.close()

    total = sum(results.values())
    print(f"[indexer] 색인 완료: {results} (총 {total}건)")
    return results


if __name__ == "__main__":
    run_all()
