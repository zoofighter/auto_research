"""
RAG 검색 인터페이스.
ChromaDB에서 종목 코드 필터링 + 의미론적 유사도 검색 수행.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from vector_db.chroma_client import get_collection, get_embedding_function, COLLECTION_NAMES

DEFAULT_TOP_K = 5
# 삼성전자 50:1 액면분할 이후 날짜 — 이전 리포트 목표주가는 현 주가와 단위가 다름
ANALYST_REPORT_MIN_DATE = "2025-11-01"


def search(
    query: str,
    stock_id: Optional[int] = None,
    top_k: int = DEFAULT_TOP_K,
    collections: list[str] = None,
    min_report_date: Optional[str] = None,
) -> list[dict]:
    """
    ChromaDB 의미론적 검색.

    Args:
        query:       검색 쿼리 텍스트
        stock_id:    SQLite stocks.id — 해당 종목 문서만 검색 (None이면 전체)
        top_k:       컬렉션당 반환 결과 수
        collections: 검색할 컬렉션 목록 (None 또는 ["all"]이면 전체)

    Returns:
        [{"content": str, "source_type": str, "source_id": int, "metadata": dict}, ...]
    """
    if collections is None or collections == ["all"]:
        target_collections = COLLECTION_NAMES
    else:
        target_collections = [c for c in collections if c in COLLECTION_NAMES]

    embed_fn = get_embedding_function()
    query_embedding = embed_fn.embed_query(query)

    results = []
    for col_name in target_collections:
        col = get_collection(col_name)
        if col.count() == 0:
            continue

        # where 조건 조합
        conditions = []
        if stock_id is not None:
            conditions.append({"stock_code": {"$eq": str(stock_id)}})
        if min_report_date and col_name == "analyst_reports":
            conditions.append({"report_date": {"$gte": min_report_date}})

        if len(conditions) == 0:
            where = None
        elif len(conditions) == 1:
            where = conditions[0]
        else:
            where = {"$and": conditions}

        try:
            res = col.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, col.count()),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            # where 필터로 결과 없을 때 fallback: 필터 없이 재시도
            try:
                res = col.query(
                    query_embeddings=[query_embedding],
                    n_results=min(top_k, col.count()),
                    include=["documents", "metadatas", "distances"],
                )
            except Exception as e:
                print(f"  [retriever] {col_name} 검색 실패: {e}")
                continue

        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        distances = res.get("distances", [[]])[0]

        for doc, meta, dist in zip(docs, metas, distances):
            results.append({
                "content": doc,
                "source_type": meta.get("source_type", col_name),
                "source_id": int(meta.get("source_id", 0)),
                "score": round(1 - dist, 4),  # cosine distance → similarity
                "metadata": meta,
            })

    # 유사도 내림차순 정렬
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k * len(target_collections)]


def search_by_text(
    texts: list[str],
    stock_id: Optional[int] = None,
    min_report_date: Optional[str] = None,
) -> list[dict]:
    """여러 질문을 순서대로 검색하여 결과를 합산한다 (question_node용)."""
    all_results = []
    seen_ids = set()
    for text in texts:
        for r in search(text, stock_id=stock_id, min_report_date=min_report_date):
            key = (r["source_type"], r["source_id"])
            if key not in seen_ids:
                seen_ids.add(key)
                all_results.append(r)
    return all_results


if __name__ == "__main__":
    results = search("삼성전자 반도체 실적", top_k=3)
    for r in results:
        print(f"[{r['source_type']}] score={r['score']:.3f}  {r['content'][:80]}")
