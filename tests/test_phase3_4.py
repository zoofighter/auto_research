"""
Phase 3 (vector_db) + Phase 4 (agents) 단위 테스트.
Ollama/ChromaDB 없이 mock으로 실행 가능.
"""

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))


# ──────────────────────────────────────────────
# Phase 3: chroma_client
# ──────────────────────────────────────────────
class TestChromaClient(unittest.TestCase):

    @patch("vector_db.chroma_client.chromadb.PersistentClient")
    def test_get_client_singleton(self, mock_client_cls):
        """get_client()는 싱글턴 인스턴스를 반환해야 한다."""
        import vector_db.chroma_client as cc
        cc._client = None  # 초기화
        mock_client_cls.return_value = MagicMock()

        c1 = cc.get_client()
        c2 = cc.get_client()
        self.assertIs(c1, c2)
        mock_client_cls.assert_called_once()
        cc._client = None  # 정리

    @patch("vector_db.chroma_client.chromadb.PersistentClient")
    def test_collection_names(self, mock_client_cls):
        """4개 컬렉션 이름이 정확해야 한다."""
        from vector_db.chroma_client import COLLECTION_NAMES
        self.assertEqual(len(COLLECTION_NAMES), 4)
        self.assertIn("analyst_reports", COLLECTION_NAMES)
        self.assertIn("dart_disclosures", COLLECTION_NAMES)
        self.assertIn("news_articles", COLLECTION_NAMES)
        self.assertIn("web_search_results", COLLECTION_NAMES)


# ──────────────────────────────────────────────
# Phase 3: retriever
# ──────────────────────────────────────────────
class TestRetriever(unittest.TestCase):

    @patch("vector_db.retriever.get_embedding_function")
    @patch("vector_db.retriever.get_collection")
    def test_search_returns_sorted_by_score(self, mock_get_col, mock_embed_fn):
        """검색 결과는 score 내림차순 정렬되어야 한다."""
        mock_embed = MagicMock()
        mock_embed.embed_query.return_value = [0.1] * 768
        mock_embed_fn.return_value = mock_embed

        mock_col = MagicMock()
        mock_col.count.return_value = 5
        mock_col.query.return_value = {
            "documents": [["doc A", "doc B"]],
            "metadatas": [[
                {"source_type": "analyst_report", "source_id": "1"},
                {"source_type": "news", "source_id": "2"},
            ]],
            "distances": [[0.1, 0.3]],  # A가 더 가까움
        }
        mock_get_col.return_value = mock_col

        from vector_db.retriever import search
        results = search("테스트 쿼리", collections=["analyst_reports"])

        self.assertGreater(results[0]["score"], results[1]["score"])

    @patch("vector_db.retriever.get_embedding_function")
    @patch("vector_db.retriever.get_collection")
    def test_empty_collection_skipped(self, mock_get_col, mock_embed_fn):
        """빈 컬렉션은 건너뛰어야 한다."""
        mock_embed = MagicMock()
        mock_embed.embed_query.return_value = [0.1] * 768
        mock_embed_fn.return_value = mock_embed

        mock_col = MagicMock()
        mock_col.count.return_value = 0  # 빈 컬렉션
        mock_get_col.return_value = mock_col

        from vector_db.retriever import search
        results = search("테스트", collections=["analyst_reports"])
        self.assertEqual(results, [])


# ──────────────────────────────────────────────
# Phase 4: State 스키마
# ──────────────────────────────────────────────
class TestStateSchema(unittest.TestCase):

    def test_supervisor_state_keys(self):
        """SupervisorState 필수 키가 존재해야 한다."""
        from agents.state.supervisor_state import SupervisorState
        required = {"date", "hitl_mode", "report_type", "watchlist",
                    "collection_done", "stock_results", "failed_stocks",
                    "comparison_draft", "final_approved"}
        self.assertTrue(required.issubset(SupervisorState.__annotations__.keys()))

    def test_stock_state_keys(self):
        """StockState 필수 키가 존재해야 한다."""
        from agents.state.stock_state import StockState
        required = {"stock_code", "company_name", "stock_id", "session_id",
                    "collected_docs", "price_context", "analysis_notes",
                    "generated_questions", "report_draft", "quality_score",
                    "iteration", "status", "hitl_mode", "force_approved"}
        self.assertTrue(required.issubset(StockState.__annotations__.keys()))


# ──────────────────────────────────────────────
# Phase 4: evaluator
# ──────────────────────────────────────────────
class TestEvaluator(unittest.TestCase):

    def test_should_loop_complete_on_high_score(self):
        """quality_score >= threshold이면 'complete'를 반환해야 한다."""
        from agents.nodes.evaluator import should_loop
        state = {"quality_score": 0.85, "iteration": 1,
                 "hitl_mode": "SEMI-AUTO", "force_approved": False}
        self.assertEqual(should_loop(state), "complete")

    def test_should_loop_complete_on_force_approved(self):
        """force_approved=True이면 점수 무관 'complete'."""
        from agents.nodes.evaluator import should_loop
        state = {"quality_score": 0.3, "iteration": 1,
                 "hitl_mode": "SEMI-AUTO", "force_approved": True}
        self.assertEqual(should_loop(state), "complete")

    def test_should_loop_complete_on_max_iteration(self):
        """MAX_ITERATIONS 도달 시 'complete'."""
        from agents.nodes.evaluator import should_loop
        import config
        state = {"quality_score": 0.3, "iteration": config.MAX_ITERATIONS,
                 "hitl_mode": "SEMI-AUTO", "force_approved": False}
        self.assertEqual(should_loop(state), "complete")

    def test_should_loop_question_on_low_score(self):
        """점수 미달 + SEMI-AUTO → 'question' 재진입."""
        from agents.nodes.evaluator import should_loop
        state = {"quality_score": 0.4, "iteration": 1,
                 "hitl_mode": "SEMI-AUTO", "force_approved": False}
        self.assertEqual(should_loop(state), "question")

    def test_should_loop_hitl_guide_on_full_review(self):
        """점수 미달 + FULL-REVIEW → 'hitl_guide'."""
        from agents.nodes.evaluator import should_loop
        state = {"quality_score": 0.4, "iteration": 1,
                 "hitl_mode": "FULL-REVIEW", "force_approved": False}
        self.assertEqual(should_loop(state), "hitl_guide")

    @patch("agents.nodes.evaluator._get_llm")
    def test_evaluate_node_returns_score(self, mock_llm_fn):
        """evaluate_node가 quality_score와 iteration을 반환해야 한다."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = "근거 충분성: 0.25\n균형성: 0.25\n구체성: 0.15\n논리성: 0.15"
        mock_llm_fn.return_value = mock_llm

        from agents.nodes.evaluator import evaluate_node
        state = {"report_draft": "테스트 보고서", "iteration": 0}
        result = evaluate_node(state)

        self.assertIn("quality_score", result)
        self.assertAlmostEqual(result["quality_score"], 0.8, places=1)
        self.assertEqual(result["iteration"], 1)


# ──────────────────────────────────────────────
# Phase 4: questioner
# ──────────────────────────────────────────────
class TestQuestioner(unittest.TestCase):

    @patch("agents.nodes.questioner._get_llm")
    def test_question_node_returns_questions(self, mock_llm_fn):
        """question_node가 질문 리스트를 반환해야 한다."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = (
            "1. 삼성전자 반도체 업황 전망은?\n"
            "2. 삼성전자 목표주가 하향 이유는?\n"
            "3. 삼성전자 외국인 매도 배경은?\n"
        )
        mock_llm_fn.return_value = mock_llm

        from agents.nodes.questioner import question_node
        state = {
            "stock_code": "005930",
            "company_name": "삼성전자",
            "analysis_notes": "분석 메모",
            "price_context": "",
            "rewrite_guide": None,
        }
        result = question_node(state)

        self.assertIn("generated_questions", result)
        self.assertGreater(len(result["generated_questions"]), 0)
        self.assertIsNone(result["rewrite_guide"])  # 소비 후 None

    @patch("agents.nodes.questioner._get_llm")
    def test_question_node_uses_rewrite_guide(self, mock_llm_fn):
        """rewrite_guide가 있으면 프롬프트에 포함되어야 한다."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = "1. 반도체 리스크 관련 질문?"
        mock_llm_fn.return_value = mock_llm

        from agents.nodes.questioner import question_node
        state = {
            "stock_code": "005930",
            "company_name": "삼성전자",
            "analysis_notes": "",
            "price_context": "",
            "rewrite_guide": "반도체 업황 리스크를 강조해줘",
        }
        result = question_node(state)
        # 프롬프트에 rewrite_guide가 포함됐는지는 mock call_args로 검증
        call_args = mock_llm.invoke.call_args[0][0]
        self.assertIn("반도체 업황 리스크를 강조해줘", call_args)


# ──────────────────────────────────────────────
# Phase 4: notifier
# ──────────────────────────────────────────────
class TestNotifier(unittest.TestCase):

    @patch("builtins.print")
    def test_notify_cli(self, mock_print):
        """CLI 모드에서 print가 호출되어야 한다."""
        import config
        original = config.HITL_NOTIFY_METHOD
        config.HITL_NOTIFY_METHOD = "cli"
        try:
            from agents.notifier import notify
            notify("테스트 알림")
            self.assertTrue(mock_print.called)
        finally:
            config.HITL_NOTIFY_METHOD = original

    def test_notify_hitl1_format(self):
        """HITL-1 알림 메시지가 종목명과 질문을 포함해야 한다."""
        from agents.notifier import notify_hitl1
        import config
        original = config.HITL_NOTIFY_METHOD
        config.HITL_NOTIFY_METHOD = "cli"
        with patch("builtins.print") as mock_print:
            notify_hitl1("005930", "삼성전자", ["질문1?", "질문2?"])
            full_output = " ".join(str(c) for c in mock_print.call_args_list)
            self.assertIn("삼성전자", full_output)
        config.HITL_NOTIFY_METHOD = original


# ──────────────────────────────────────────────
# Phase 4: graph 빌드 검증
# ──────────────────────────────────────────────
class TestGraphBuilds(unittest.TestCase):

    def test_collection_agent_builds(self):
        """CollectionAgent 그래프가 오류 없이 빌드되어야 한다."""
        from agents.collection_agent import build_collection_agent
        agent = build_collection_agent()
        self.assertIsNotNone(agent)

    def test_stock_agent_builds(self):
        """StockAgent 그래프가 오류 없이 빌드되어야 한다."""
        from agents.stock_agent import build_stock_agent
        agent = build_stock_agent()
        self.assertIsNotNone(agent)

    def test_supervisor_builds(self):
        """Supervisor 그래프가 오류 없이 빌드되어야 한다."""
        from agents.supervisor import build_supervisor
        sup = build_supervisor()
        self.assertIsNotNone(sup)


if __name__ == "__main__":
    unittest.main(verbosity=2)
