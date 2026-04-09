"""
전역 설정 — 환경변수로 오버라이드 가능.

사용 예:
  import config
  print(config.OLLAMA_MODEL)
  print(config.HITL_MODE)
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

# ── 경로 ──────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
REPORTDB_DIR = Path("/Users/boon/reportdb")
DB_PATH    = REPORTDB_DIR / "stock_analysis.db"
CHROMA_DIR = REPORTDB_DIR / "chroma"
PDF_DIR    = Path("/Users/boon/report")
REPORT_DIR = BASE_DIR / "reports"

REPORTDB_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(exist_ok=True)

# ── LLM / 임베딩 ───────────────────────────────────────────────
OLLAMA_BASE_URL  = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL     = os.environ.get("OLLAMA_MODEL", "qwen3:1.7b")
EMBED_MODEL      = os.environ.get("EMBED_MODEL", "rjmalagon/gte-qwen2-1.5b-instruct-embed-f16:latest")

# ── 외부 API ──────────────────────────────────────────────────
DART_API_KEY     = os.environ.get("DART_API_KEY", "")

# ── 분석 파라미터 ──────────────────────────────────────────────
QUALITY_THRESHOLD   = float(os.environ.get("QUALITY_THRESHOLD", "0.7"))
MAX_ITERATIONS      = int(os.environ.get("MAX_ITERATIONS", "3"))
MAX_WATCHLIST       = int(os.environ.get("MAX_WATCHLIST", "10"))
MAX_PARALLEL_AGENTS = int(os.environ.get("MAX_PARALLEL_AGENTS", "3"))  # Ollama 동시 호출 제한

# ── HITL 설정 ─────────────────────────────────────────────────
HITL_MODE            = os.environ.get("HITL_MODE", "SEMI-AUTO")   # FULL-AUTO / SEMI-AUTO / FULL-REVIEW
HITL_TIMEOUT_Q       = int(os.environ.get("HITL_TIMEOUT_Q", "30"))       # 분
HITL_TIMEOUT_DRAFT   = int(os.environ.get("HITL_TIMEOUT_DRAFT", "120"))  # 분
HITL_TIMEOUT_FINAL   = int(os.environ.get("HITL_TIMEOUT_FINAL", "240"))  # 분
HITL_TIMEOUT_GUIDE   = int(os.environ.get("HITL_TIMEOUT_GUIDE", "60"))   # 분
HITL_NOTIFY_METHOD   = os.environ.get("HITL_NOTIFY_METHOD", "telegram")  # telegram / cli / none

# ── 보고서 기본 양식 ───────────────────────────────────────────
DEFAULT_REPORT_TYPE  = os.environ.get("DEFAULT_REPORT_TYPE", "full_analysis")
