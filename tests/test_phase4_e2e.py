"""
Phase 4 E2E: StockAgent FULL-AUTO 모드로 삼성전자 1회 실행.
HITL 없이 FULL-AUTO로 돌려서 report_draft까지 생성 확인.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
config.HITL_MODE = "FULL-AUTO"
config.HITL_NOTIFY_METHOD = "cli"
config.MAX_ITERATIONS = 1  # 빠른 테스트용

from db.base import init_db, SessionLocal
from db.models.stock import Stock

init_db()

# stock_id 조회
session = SessionLocal()
try:
    stock = session.query(Stock).filter_by(stock_code="005930").first()
    stock_id = stock.id
    company_name = stock.company_name
finally:
    session.close()

print(f"=== Phase 4 E2E: {company_name}({stock_id}) FULL-AUTO ===\n")

from agents.stock_agent import build_stock_agent

agent = build_stock_agent()

initial_state = {
    "stock_code": "005930",
    "company_name": "삼성전자",
    "stock_id": stock_id,
    "session_id": 0,
    "collected_docs": [],
    "price_context": "",
    "analysis_notes": "",
    "generated_questions": [],
    "report_draft": "",
    "quality_score": 0.0,
    "iteration": 0,
    "status": "pending",
    "hitl_mode": "FULL-AUTO",
    "force_approved": False,
    "rewrite_guide": None,
    "report_type": "full_analysis",
}

print("StockAgent 실행 중...")
result = agent.invoke(initial_state)

print(f"\n✅ 실행 완료!")
print(f"   iteration: {result.get('iteration')}")
print(f"   quality_score: {result.get('quality_score')}")
print(f"   질문 수: {len(result.get('generated_questions', []))}")
draft = result.get('report_draft', '')
print(f"   보고서 길이: {len(draft)}자")
print(f"\n--- 보고서 초안 (앞 500자) ---")
print(draft[:500])
