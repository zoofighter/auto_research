"""
ChromaDB 연결 및 4개 컬렉션 초기화.
임베딩: Ollama nomic-embed-text (로컬, 외부 API 불필요)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import chromadb
from chromadb import Collection
from langchain_ollama import OllamaEmbeddings

import config

COLLECTION_NAMES = [
    "analyst_reports",
    "dart_disclosures",
    "news_articles",
    "web_search_results",
]

_client: chromadb.PersistentClient | None = None
_embed_fn = None


def get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    return _client


def get_embedding_function():
    """OllamaEmbeddings — Ollama 미실행 시 None 반환 (indexer에서 처리)."""
    global _embed_fn
    if _embed_fn is None:
        _embed_fn = OllamaEmbeddings(
            base_url=config.OLLAMA_BASE_URL,
            model=config.EMBED_MODEL,
        )
    return _embed_fn


def get_collection(name: str) -> Collection:
    """컬렉션을 가져오거나 없으면 생성한다."""
    client = get_client()
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def init_collections() -> dict[str, Collection]:
    """4개 컬렉션을 초기화하고 반환한다."""
    return {name: get_collection(name) for name in COLLECTION_NAMES}


def collection_stats() -> dict[str, int]:
    """각 컬렉션의 문서 수를 반환한다."""
    result = {}
    for name in COLLECTION_NAMES:
        try:
            col = get_collection(name)
            result[name] = col.count()
        except Exception:
            result[name] = -1
    return result


if __name__ == "__main__":
    cols = init_collections()
    stats = collection_stats()
    print("ChromaDB 컬렉션 초기화 완료:")
    for name, count in stats.items():
        print(f"  {name}: {count}개 문서")
