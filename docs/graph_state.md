# 그래프 상태(Graph State) 상세 설계

**작성일:** 2026-04-08  
**버전:** 1.0  
**연관 문서:** implementation_plan.md, diagrams.md

---

## 1. State란 무엇인가

LangGraph에서 State는 **그래프 실행 중 모든 노드가 공유하는 데이터 구조**다.  
노드는 State를 입력받아 변경된 필드만 반환하며, LangGraph가 이를 기존 State에 병합(merge)한다.

```
노드 실행 원리:

  현재 State  →  [노드 함수]  →  변경된 필드만 반환
      ↑                               ↓
      └──────── LangGraph merge ───────┘
```

노드끼리 직접 호출하지 않고, State를 통해서만 데이터를 주고받는다.  
이 덕분에 노드를 독립적으로 테스트하고 교체할 수 있다.

---

## 2. 이 시스템의 State 2계층 구조

```
SupervisorState          ← Supervisor 그래프 전체 공유
      │
      └── StockState × N ← 종목별 독립 인스턴스 (Send() API로 복제)
```

---

## 3. SupervisorState

**위치:** `agents/state/supervisor_state.py`  
**소유자:** SupervisorAgent  
**생명주기:** daily_runner.py 실행 시작 ~ 전체 파이프라인 완료

### 필드 정의

| 필드 | 타입 | 초기값 | 설명 |
|------|------|--------|------|
| `date` | str | 오늘 날짜 | 실행 기준일 (YYYY-MM-DD) |
| `hitl_mode` | str | config값 | FULL-AUTO / SEMI-AUTO / FULL-REVIEW |
| `report_type` | str | "full_analysis" | 보고서 양식 (아래 참조) |
| `watchlist` | list[str] | DB 조회 | 분석 대상 stock_code 목록 |
| `collection_done` | bool | False | CollectionAgent 완료 여부 |
| `stock_results` | list[dict] | [] | StockAgent 결과 누적 |
| `failed_stocks` | list[str] | [] | 실패한 종목 코드 목록 |
| `comparison_draft` | str\|None | None | report_type="comparison" 시 집계 비교 보고서 |
| `final_approved` | bool | False | HITL-3 최종 승인 여부 |

### report_type 값 정의

| 값 | 설명 | 주요 섹션 |
|----|------|-----------|
| `full_analysis` | 심층 분석 (기본값) | Executive Summary + 전체 섹션 + 출처 |
| `daily_brief` | 일일 브리프 | 변화 요약 3줄 + 주요 이벤트 + 액션 포인트 |
| `risk_focus` | 리스크 집중 | 리스크 항목 추출·등급화 (단기/중장기) |
| `comparison` | 비교 분석 | 복수 종목 나란히 비교 (watchlist 전체) |
| `earnings` | 실적 시즌 | 컨센서스 vs 실제 실적 차이 중심 |
| `event_brief` | 공시 긴급 | 주요 공시 1건 집중 해석 |

`report_type`은 `init_node`에서 설정되며, `SupervisorState` → `StockState`로 주입된다.  
`synthesize_node`가 이 값을 읽어 해당 프롬프트 템플릿을 선택한다.

### stock_results 항목 구조

```
{
  "stock_code":    "005930",
  "company_name":  "삼성전자",
  "status":        "completed",   # completed / failed / skipped
  "quality_score": 0.83,
  "draft":         "## Executive Summary\n...",
  "session_id":    42
}
```

### 노드별 State 변경

```
init_node
  → date, hitl_mode, watchlist 설정
  → collection_done = False, stock_results = [], failed_stocks = []

collection_node (CollectionAgent 완료 후)
  → collection_done = True

aggregate_node (모든 StockAgent 완료 후)
  → stock_results = [{...}, {...}, ...]
  → failed_stocks = ["000660"]  (실패 종목만)
  → report_type = "comparison" 일 때:
       comparison_draft = LLM이 stock_results 전체를 병합해 비교 보고서 생성

hitl_final_node
  → final_approved = True (approve 시)
```

---

## 4. StockState

**위치:** `agents/state/stock_state.py`  
**소유자:** StockAnalysisAgent 인스턴스 (종목당 1개)  
**생명주기:** dispatch_node의 Send() 호출 ~ complete_node 반환

### 4-1. 식별 필드

| 필드 | 타입 | 초기값 | 설명 |
|------|------|--------|------|
| `stock_code` | str | Supervisor 주입 | 종목코드 (예: 005930) |
| `company_name` | str | Supervisor 주입 | 회사명 |
| `session_id` | int | None → DB 생성 | analysis_sessions.id |
| `report_type` | str | Supervisor 주입 | 보고서 양식 (SupervisorState에서 전달) |

### 4-2. 분석 데이터 필드

| 필드 | 타입 | 초기값 | 채우는 노드 |
|------|------|--------|-----------|
| `collected_docs` | list[dict] | [] | analyze_node (RAG 수집) |
| `analysis_notes` | str | "" | analyze_node |
| `generated_questions` | list[str] | [] | question_node |
| `search_results` | list[dict] | [] | search_node |
| `report_draft` | str | "" | synthesize_node |

#### collected_docs 항목 구조

```
{
  "content":     "삼성전자 3분기 영업이익 10.3조...",
  "source_type": "analyst_report",  # analyst_report / dart / news / web
  "source_id":   42,                # SQLite 해당 테이블 id
  "metadata": {
    "firm_name":   "삼성증권",
    "report_date": "2026-03-15",
    "page_num":    3
  }
}
```

### 4-3. 제어 필드

| 필드 | 타입 | 초기값 | 설명 |
|------|------|--------|------|
| `quality_score` | float | 0.0 | evaluate_node가 0.0~1.0 산정 |
| `iteration` | int | 0 | 루프 카운터. 최대 3회 |
| `status` | str | "running" | running / completed / failed / skipped |

### 4-4. HITL 필드

| 필드 | 타입 | 초기값 | 설명 |
|------|------|--------|------|
| `hitl_mode` | str | Supervisor 주입 | 운영 모드 |
| `human_q_feedback` | dict\|None | None | HITL-1 응답 수신 후 채워짐 |
| `human_draft_feedback` | dict\|None | None | HITL-2 응답 수신 후 채워짐 |
| `rewrite_guide` | str\|None | None | HITL-4 재작성 방향 가이드 |
| `force_approved` | bool | False | 품질 미달 강제 승인 여부 |

#### human_q_feedback 구조

```
{
  "action":            "edit",            # approve / edit / add / skip / timeout
  "revised_questions": ["새 질문1", "새 질문2"],  # edit/add 시만 존재
  "responded_at":      "2026-04-08T18:42:00"
}
```

#### human_draft_feedback 구조

```
{
  "action":        "rewrite",             # approve / edit / rewrite / timeout
  "revised_draft": None,                  # edit 시 수정된 전문
  "guide":         "반도체 업황 리스크를 더 강조해줘",  # rewrite 시 방향 가이드
  "responded_at":  "2026-04-08T19:15:00"
}
```

---

## 5. 노드별 State 변경 흐름 (StockAgent)

```
dispatch_node
  └─ Send() → StockState 초기화 (stock_code, company_name, hitl_mode 주입)
              session_id = None

analyze_node
  └─ session_id = DB INSERT(analysis_sessions) 결과
  └─ collected_docs = RAG 검색 결과 리스트
  └─ analysis_notes = LLM 분석 메모

question_node
  └─ generated_questions = ["질문1", "질문2", "질문3"]
  └─ rewrite_guide 있으면 해당 방향 반영 후 None으로 초기화

hitl_q_node  (HITL-1)
  └─ interrupt() 호출 → 사람 입력 대기
  └─ human_q_feedback = {action, revised_questions, ...} 수신
  └─ action="edit" → generated_questions = revised_questions
  └─ action="skip" → status = "skipped" → complete_node로 직행

search_node
  └─ search_results = 웹 검색 결과 리스트
  └─ collected_docs += 검색 결과 (RAG 추가 주입)

synthesize_node
  └─ report_draft = 완성된 보고서 초안 (Markdown)

hitl_draft_node  (HITL-2)
  └─ interrupt() 호출 → 사람 입력 대기
  └─ human_draft_feedback = {action, revised_draft or guide, ...} 수신
  └─ action="edit"    → report_draft = revised_draft
  └─ action="rewrite" → rewrite_guide = guide → question_node 재진입

evaluate_node
  └─ quality_score = 0.0~1.0 (4개 항목 합산)
  └─ iteration += 1

hitl_guide_node  (HITL-4, 품질 미달 시)
  └─ interrupt() 호출 → 사람 입력 대기
  └─ action="guide"         → rewrite_guide = 입력 텍스트 → question_node 재진입
  └─ action="force_approve" → force_approved = True → complete_node 직행
  └─ timeout               → rewrite_guide = None  → question_node 재진입

complete_node
  └─ status = "completed"
  └─ DB 저장 (generated_reports, report_sources)
  └─ StockResult 반환 → SupervisorState.stock_results 누적
```

---

## 6. Send()로 State가 복제되는 방식

`dispatch_node`에서 watchlist 종목 수만큼 StockState 인스턴스가 생성되며, 각각은 완전히 독립된 메모리 공간에서 실행된다.

```
SupervisorState.watchlist = ["005930", "000660", "035420"]

dispatch_node:
  Send("stock_agent", StockState(stock_code="005930"))  → 인스턴스 A
  Send("stock_agent", StockState(stock_code="000660"))  → 인스턴스 B
  Send("stock_agent", StockState(stock_code="035420"))  → 인스턴스 C

  ┌─────────────────────────────────────────────────┐
  │  인스턴스 A      인스턴스 B      인스턴스 C     │
  │  질문 생성 중    웹 검색 중      초안 작성 중   │  ← 동시 실행
  │  HITL-1 대기    완료            HITL-2 대기    │
  └─────────────────────────────────────────────────┘

  A의 quality_score 변경이 B, C에 영향 없음
  A 실패 시 B, C는 계속 진행
```

---

## 7. State와 DB의 관계

State는 **휘발성(메모리)**, DB는 **영속성**이다.  
노드가 State를 변경할 때 필요한 항목은 즉시 DB에도 기록하여 그래프 재시작 시 복원 가능하다.

```
State 필드                    DB 테이블·컬럼
─────────────────────────────────────────────────────
stock_code                 →  stocks.stock_code
session_id                 →  analysis_sessions.id
generated_questions        →  analysis_sessions.generated_questions (JSON)
status                     →  analysis_sessions.status
iteration                  →  analysis_sessions.iteration_count
quality_score              →  generated_reports.quality_score
report_draft               →  generated_reports.executive_summary (요약)
human_q_feedback           →  hitl_feedbacks (action, revised_content, ...)
human_draft_feedback       →  hitl_feedbacks
rewrite_guide              →  (question_node 소비 후 None, 별도 저장 없음)
force_approved             →  hitl_feedbacks.action = "force_approved"
```

### 재시작 복원 규칙

```
analysis_sessions.status = "running"
  → 비정상 종료로 판단
  → session_id로 State 일부 복원 후 마지막 완료 노드부터 재개 가능

analysis_sessions.status = "completed" / "failed" / "skipped"
  → 재실행 시 해당 세션 스킵 (멱등성 보장)
```

---

## 8. HITL과 State의 상호작용

`interrupt()`는 State를 그대로 보존한 채 그래프를 일시 중단한다.  
사람이 응답을 보내면 LangGraph가 해당 State에 피드백을 주입하고 중단 지점부터 재개한다.

```
[HITL-2 흐름]

synthesize_node 완료
  → State.report_draft = "## Executive Summary\n삼성전자는..."
  → hitl_draft_node 진입
  → interrupt() 호출
  → State 보존된 채 중단 (Telegram 알림 발송)

──── 사람이 2시간 내 응답 ────

응답: {action: "rewrite", guide: "반도체 리스크 강조"}
  → State.human_draft_feedback = {action: "rewrite", guide: "..."}
  → State.rewrite_guide = "반도체 리스크 강조"
  → hitl_draft_node 재개
  → conditional_edge: rewrite → question_node 재진입

question_node
  → State.rewrite_guide 읽어 질문 생성 방향 반영
  → State.rewrite_guide = None (소비 완료)
```

---

## 9. State 필드 변경 규칙 요약

| 규칙 | 설명 |
|------|------|
| **단방향 누적** | `collected_docs`, `search_results`는 노드가 추가만 하고 삭제하지 않음 |
| **소비 후 초기화** | `rewrite_guide`는 question_node가 읽은 뒤 None으로 초기화 |
| **한 번만 설정** | `session_id`, `stock_code`는 초기화 이후 변경 없음 |
| **루프 상한** | `iteration`이 3에 도달하면 evaluate_node가 강제 complete_node 진행 |
| **격리** | StockState 인스턴스 간 State 공유 없음. SupervisorState에만 결과 반환 |
