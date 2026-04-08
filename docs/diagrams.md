# 시스템 다이어그램

**작성일:** 2026-04-08  
**버전:** 1.2 (멀티 에이전트 전환)

---

## 1. 전체 시스템 아키텍처 (멀티 에이전트)

```mermaid
graph TB
    subgraph Sources["📥 데이터 소스"]
        S1[네이버 금융\n리포트 PDF]
        S2[DART Open API]
        S3[네이버 주식\n재무 지표]
        S4[네이버 뉴스]
    end

    subgraph Infra["🗄️ 공유 인프라"]
        DB[(SQLite\n11개 테이블)]
        VDB[(ChromaDB\n4개 컬렉션)]
        LLM[🦙 Qwen\nOllama 로컬]
    end

    subgraph Supervisor["🎯 SupervisorAgent (supervisor.py)"]
        SUP[Supervisor\nGraph]
    end

    subgraph ColAgent["🔄 CollectionAgent (collection_agent.py)"]
        CA1[naver_report_node]
        CA2[dart_node]
        CA3[financial_node]
        CA4[news_node]
        CA5[indexer_node]
    end

    subgraph StockAgents["🤖 StockAnalysisAgent × N (stock_agent.py)\n병렬 실행 — Send() API"]
        SA1["StockAgent\n종목 1"]
        SA2["StockAgent\n종목 2"]
        SA3["StockAgent\n종목 N"]
    end

    subgraph OutAgent["📄 OutputAgent (output_agent.py)"]
        OA1[markdown_node]
        OA2[pdf_node]
        OA3[ppt_node]
    end

    subgraph Final["📦 최종 출력물"]
        F1[📝 Report.md]
        F2[📄 Report.pdf]
        F3[📊 Report.pptx]
    end

    S1 & S2 & S3 & S4 --> ColAgent
    ColAgent --> DB
    ColAgent --> VDB

    SUP --> ColAgent
    SUP -- "Send() ×N" --> StockAgents
    SUP --> OutAgent

    StockAgents <--> LLM
    StockAgents <--> VDB
    StockAgents <--> DB

    OutAgent --> DB
    OutAgent --> F1 & F2 & F3
```

---

## 2. 데이터 수집 흐름

```mermaid
sequenceDiagram
    participant S as Scheduler
    participant NR as naver_report.py
    participant DA as dart_api.py
    participant NF as naver_financial.py
    participant NC as news_collector.py
    participant DB as SQLite
    participant IDX as indexer.py
    participant VDB as ChromaDB

    S->>NR: 실행 (today_only=True)
    NR->>NR: 네이버 금융 스크래핑
    NR->>DB: analyst_reports INSERT
    NR->>DB: is_processed = false

    S->>DA: 실행 (watchlist 종목)
    DA->>DA: DART API 호출
    DA->>DB: dart_disclosures INSERT (rcept_no UNIQUE)

    S->>NF: 실행 (watchlist 종목)
    NF->>NF: 네이버 주식 스크래핑
    NF->>DB: financial_metrics INSERT (UNIQUE: stock_id + date)

    S->>NC: 실행 (watchlist 종목 최대 10개)
    NC->>NC: 뉴스 수집
    NC->>NC: LLM으로 relevance_score 산정
    NC->>DB: news_articles INSERT (score >= 0.5만)

    S->>IDX: ChromaDB 색인 실행
    IDX->>DB: is_processed=false 조회
    IDX->>IDX: PDF 청크 분할 (500 토큰)
    IDX->>VDB: upsert (4개 컬렉션)
    IDX->>DB: is_processed = true 업데이트
```

---

## 3. DB 관계도 (ERD)

```mermaid
erDiagram
    stocks {
        int id PK
        string stock_code UK
        string company_name
        string sector
        string market_cap_category
        bool is_watchlist
        datetime created_at
        datetime updated_at
    }

    analyst_reports {
        int id PK
        int stock_id FK
        string title
        string firm_name
        string analyst_name
        date report_date
        string pdf_url
        string pdf_path
        bool is_processed
        datetime created_at
    }

    analyst_opinions {
        int id PK
        int report_id FK
        int stock_id FK
        string opinion
        float price_target
        float prev_price_target
        datetime created_at
    }

    financial_metrics {
        int id PK
        int stock_id FK
        date metric_date
        float per
        float pbr
        float roe
        float debt_ratio
        float market_cap
        float foreign_shareholding_pct
        datetime created_at
    }

    dart_disclosures {
        int id PK
        int stock_id FK
        string rcept_no UK
        string disclosure_type
        string title
        date rcept_dt
        bool is_major_event
        datetime created_at
    }

    news_articles {
        int id PK
        int stock_id FK
        string headline
        string url
        float relevance_score
        string summary
        datetime published_at
        datetime created_at
    }

    analysis_sessions {
        int id PK
        int stock_id FK
        datetime started_at
        datetime completed_at
        string status
        int iteration_count
        text generated_questions
        datetime created_at
    }

    web_search_results {
        int id PK
        int session_id FK
        text question
        string query
        string result_url
        text result_snippet
        datetime created_at
    }

    generated_reports {
        int id PK
        int stock_id FK
        int session_id FK
        date report_date
        text executive_summary
        string report_md_path
        string report_pdf_path
        string ppt_path
        float quality_score
        datetime created_at
    }

    report_sources {
        int id PK
        int generated_report_id FK
        string source_type
        int source_id
        text excerpt
        datetime created_at
    }

    stocks ||--o{ analyst_reports : "has"
    stocks ||--o{ analyst_opinions : "has"
    stocks ||--o{ financial_metrics : "has"
    stocks ||--o{ dart_disclosures : "has"
    stocks ||--o{ news_articles : "has"
    stocks ||--o{ analysis_sessions : "has"
    stocks ||--o{ generated_reports : "has"
    analyst_reports ||--o{ analyst_opinions : "generates"
    analysis_sessions ||--o{ web_search_results : "produces"
    analysis_sessions ||--|| generated_reports : "outputs"
    generated_reports ||--o{ report_sources : "cites"
```

---

## 4. Supervisor 오케스트레이션 — 멀티 에이전트 흐름

```mermaid
flowchart TD
    START([▶ START]) --> INIT

    INIT["🔧 init_node\n날짜·HITL 모드·watchlist 초기화"]
    INIT --> COLLECT

    subgraph COLLECT["🔄 CollectionAgent (순차)"]
        direction LR
        CA1[naver_report] --> CA2[dart]
        CA2 --> CA3[financial]
        CA3 --> CA4[news]
        CA4 --> CA5[indexer]
    end

    COLLECT --> DISPATCH["📤 dispatch_node\nSend() × watchlist 종목 수"]

    DISPATCH --> SA1 & SA2 & SA3

    subgraph PARALLEL["🤖 StockAnalysisAgent × N (병렬)"]
        SA1["StockAgent\n종목 1"]
        SA2["StockAgent\n종목 2"]
        SA3["StockAgent\n종목 N"]
    end

    SA1 & SA2 & SA3 --> AGG["📊 aggregate_node\n전체 결과 수집·실패 종목 식별"]

    AGG --> OUTPUT

    subgraph OUTPUT["📄 OutputAgent (순차)"]
        direction LR
        OA1[markdown] --> OA2[pdf]
        OA2 --> OA3[ppt]
        OA3 --> OA4[summary]
    end

    OUTPUT --> HITL3["⛔ HITL-3\n전체 최종 승인\n(Supervisor 레벨)"]
    HITL3 -- "approve / timeout" --> END([⏹ END])
    HITL3 -- "reject" --> OUTPUT

    style DISPATCH fill:#cfe2ff,stroke:#0d6efd
    style HITL3 fill:#d1e7dd,stroke:#198754
```

---

## 4-1. StockAnalysisAgent 내부 상태 그래프 (HITL 포함)

```mermaid
stateDiagram-v2
    [*] --> analyze_node : StockAgent 시작\n(StockState 수신)

    analyze_node --> question_node : RAG 수집 + 분석 완료

    question_node --> HITL_Q : 자율 질문 3~5개 생성

    state HITL_Q {
        [*] --> waiting_q : ⛔ HITL-1 질문 검토\n(30분 타임아웃)
        waiting_q --> approved_q : approve / timeout
        waiting_q --> edited_q : edit / add
        waiting_q --> skipped : skip
    }

    HITL_Q --> search_node : approve / edit / timeout
    HITL_Q --> [*] : skip → status=skipped

    search_node --> synthesize_node : 웹 검색 완료

    synthesize_node --> HITL_DRAFT : 보고서 초안 완성

    state HITL_DRAFT {
        [*] --> waiting_d : ⛔ HITL-2 초안 검토\n(2시간 타임아웃)
        waiting_d --> approved_d : approve / timeout
        waiting_d --> edited_d : edit
        waiting_d --> rewrite_req : rewrite
    }

    HITL_DRAFT --> evaluate_node : approve / edit / timeout
    HITL_DRAFT --> question_node : rewrite (루프 재진입)

    evaluate_node --> HITL_GUIDE : quality_score < 0.7\n& iteration < 3

    state HITL_GUIDE {
        [*] --> waiting_g : ⛔ HITL-4 재작성 지시\n(1시간 타임아웃)
        waiting_g --> guided : guide 입력 / timeout
        waiting_g --> force_ok : force_approve
    }

    HITL_GUIDE --> question_node : guided (iteration++)
    HITL_GUIDE --> complete_node : force_approve

    evaluate_node --> complete_node : quality_score ≥ 0.7\n또는 force_approved

    complete_node --> [*] : Supervisor에 결과 반환\n{status, quality_score, draft}
```

---

## 5. StockAnalysisAgent 노드별 상세 처리 흐름

```mermaid
flowchart TD
    START([▶ StockAgent 시작\nStockState 수신]) --> INIT

    INIT["🔧 초기화\n- analysis_sessions 생성\n- status = running\n- iteration = 0"]

    INIT --> COLLECT

    subgraph COLLECT["📚 collect_node — RAG 초기 수집"]
        C1["ChromaDB 쿼리\nfilter: stock_code"] --> C2
        C2["analyst_reports 컬렉션\n→ 최근 1년 리포트 top_k=10"] --> C3
        C3["dart_disclosures 컬렉션\n→ 최근 6개월 공시 top_k=5"] --> C4
        C4["news_articles 컬렉션\n→ 최근 30일 뉴스 top_k=10"]
    end

    COLLECT --> ANALYZE

    subgraph ANALYZE["🔬 analyze_node — 심층 문서 분석"]
        A1["투자의견 변화 추적\nBuy→Hold→Sell 시계열"] --> A2
        A2["목표주가 트렌드\n상향/하향 횟수, 범위"] --> A3
        A3["핵심 리스크 키워드 추출\n(LLM NER)"] --> A4
        A4["재무 지표 이상치 탐지\nfinancial_metrics 조회"] --> A5
        A5["경쟁사 비교 포인트 추출\n(리포트 내 언급 경쟁사)"]
    end

    ANALYZE --> QUESTION

    subgraph QUESTION["❓ question_node — 자율 질문 생성"]
        Q1["분석 공백 탐지\n(불확실 항목 식별)"] --> Q2
        Q2["질문 생성 프롬프트\n'추가 확인 필요한 사항을\n검색 질문으로 3~5개 생성'"] --> Q3
        Q3["질문 구체화\n종목명·기간·비교 대상 포함"] --> Q4
        Q4["rewrite_guide 있으면\n해당 방향 반영"] --> Q5
        Q5["generated_questions\n→ analysis_sessions 업데이트"]
    end

    QUESTION --> HITL1

    subgraph HITL1["⛔ HITL-1: hitl_q_node — 질문 검토"]
        H1A["Telegram / CLI 알림 발송\n(질문 목록 전송)"] --> H1B
        H1B["interrupt()\n그래프 일시 중단"] --> H1C
        H1C{"사람 입력\n또는 30분 타임아웃"}
        H1C -- "approve\n또는 timeout" --> H1D["질문 그대로 유지"]
        H1C -- "edit / add" --> H1E["state.generated_questions\n수정 반영"]
        H1C -- "skip" --> H1F["분석 중단\nstatus=skipped"]
        H1D --> H1G["hitl_feedbacks INSERT"]
        H1E --> H1G
    end

    HITL1 -- "approve / edit / timeout" --> SEARCH
    HITL1 -- "skip" --> ENDEARLY([⏹ 분석 중단])

    subgraph SEARCH["🌐 search_node — 웹 검색 실행"]
        SR1["질문별 검색어 최적화\n(LLM 쿼리 재작성)"] --> SR2
        SR2["DuckDuckGo / SerpAPI\n검색 실행"] --> SR3
        SR3["결과 관련성 필터링\n(relevance_score ≥ 0.4)"] --> SR4
        SR4["web_search_results\n테이블 INSERT"] --> SR5
        SR5["ChromaDB\nweb_search_results 컬렉션\n추가 색인"]
    end

    SEARCH --> SYNTHESIZE

    subgraph SYNTHESIZE["✍️ synthesize_node — 보고서 초안 작성"]
        SY1["전체 컨텍스트 통합\n(RAG 결과 + 검색 결과)"] --> SY2
        SY2["섹션별 초안 생성\n(Executive Summary 먼저)"] --> SY3
        SY3["재무 데이터 삽입\nfinancial_metrics 직접 조회"] --> SY4
        SY4["출처 매핑\n각 주장 → source_id 연결"] --> SY5
        SY5["report_draft\n완성 (Markdown 형식)"]
    end

    SYNTHESIZE --> HITL2

    subgraph HITL2["⛔ HITL-2: hitl_draft_node — 초안 검토"]
        H2A["Telegram / CLI 알림 발송\n(Executive Summary + 링크)"] --> H2B
        H2B["interrupt()\n그래프 일시 중단"] --> H2C
        H2C{"사람 입력\n또는 2시간 타임아웃"}
        H2C -- "approve / timeout" --> H2D["초안 그대로 evaluate로"]
        H2C -- "edit" --> H2E["state.report_draft\n직접 수정 반영"]
        H2C -- "rewrite + guide" --> H2F["state.rewrite_guide 저장\n→ question_node 재진입"]
        H2D --> H2G["hitl_feedbacks INSERT"]
        H2E --> H2G
        H2F --> H2G
    end

    HITL2 -- "approve / edit / timeout" --> EVALUATE
    HITL2 -- "rewrite" --> QUESTION

    subgraph EVALUATE["⚖️ evaluate_node — 품질 평가"]
        E1["근거 충분성 평가\n(0 ~ 0.3점)"] --> E2
        E2["균형성 평가\n(0 ~ 0.3점)"] --> E3
        E3["구체성 평가\n(0 ~ 0.2점)"] --> E4
        E4["논리성 평가\n(0 ~ 0.2점)"] --> E5
        E5["quality_score 합산\n0.0 ~ 1.0"]
    end

    EVALUATE --> BRANCH{{"🔀 분기\nquality_score ≥ 0.7\n또는 force_approved?"}}

    BRANCH -- "YES" --> HITL3

    subgraph HITL3["⛔ HITL-3: hitl_final_node — 최종 승인"]
        H3A["최종 승인 요청 알림"] --> H3B
        H3B["interrupt()\n4시간 타임아웃"] --> H3C
        H3C{"사람 입력"}
        H3C -- "approve / timeout" --> H3D["hitl_feedbacks INSERT"]
        H3C -- "reject" --> H3E["HITL-2로 복귀"]
    end

    HITL3 -- "approve / timeout" --> OUTPUT
    HITL3 -- "reject" --> HITL2

    BRANCH -- "NO\niteration < 3" --> HITL4

    subgraph HITL4["⛔ HITL-4: hitl_guide_node — 재작성 지시"]
        H4A["품질 미달 알림\n(quality_score 전송)"] --> H4B
        H4B["interrupt()\n1시간 타임아웃"] --> H4C
        H4C{"사람 입력"}
        H4C -- "guide 입력 / timeout" --> H4D["rewrite_guide 저장\niteration++"]
        H4C -- "force_approve" --> H4E["force_approved=true"]
        H4D --> H4F["hitl_feedbacks INSERT"]
        H4E --> H4F
    end

    HITL4 -- "guide / timeout" --> QUESTION
    HITL4 -- "force_approve" --> OUTPUT

    subgraph COMPLETE["✅ complete_node — Supervisor에 결과 반환"]
        O1["generated_reports INSERT\n(draft, quality_score)"] --> O2
        O2["report_sources INSERT\n(출처 audit trail)"] --> O3
        O3["analysis_sessions 업데이트\nstatus = completed"]
        O3 --> O4["StockResult 반환\n{stock_code, status,\nquality_score, draft}"]
    end

    COMPLETE --> END([⏹ StockAgent 종료\nSupervisor aggregate_node로])

    style HITL1 fill:#fff3cd,stroke:#ffc107
    style HITL2 fill:#fff3cd,stroke:#ffc107
    style HITL4 fill:#f8d7da,stroke:#dc3545
    style BRANCH fill:#e2e3e5,stroke:#6c757d
    style EVALUATE fill:#f8d7da,stroke:#dc3545
    style COMPLETE fill:#d1e7dd,stroke:#198754
    style START fill:#cfe2ff,stroke:#0d6efd
    style END fill:#cfe2ff,stroke:#0d6efd
    style ENDEARLY fill:#e2e3e5,stroke:#6c757d
```

---

## 6. 멀티 에이전트 State 구조

```mermaid
flowchart TB
    subgraph SUP_STATE["📋 SupervisorState\n(supervisor.py 보유)"]
        direction TB
        SS1["date: str"]
        SS2["hitl_mode: str"]
        SS3["watchlist: list[str]"]
        SS4["collection_done: bool"]
        SS5["stock_results: list[dict]\n{stock_code, status,\n quality_score, draft}"]
        SS6["failed_stocks: list[str]"]
        SS7["final_approved: bool"]
    end

    subgraph STOCK_STATE["📋 StockState\n(stock_agent.py 인스턴스별 독립 보유)"]
        direction TB
        SK1["stock_code: str"]
        SK2["company_name: str"]
        SK3["session_id: int"]
        SK4["collected_docs: list[dict]"]
        SK5["analysis_notes: str"]
        SK6["generated_questions: list[str]"]
        SK7["search_results: list[dict]"]
        SK8["report_draft: str"]
        SK9["quality_score: float"]
        SK10["iteration: int"]
        SK11["status: str"]
        SK12["hitl_mode: str"]
        SK13["human_q_feedback: dict|None"]
        SK14["human_draft_feedback: dict|None"]
        SK15["rewrite_guide: str|None"]
        SK16["force_approved: bool"]
    end

    subgraph FLOW["🔄 State 흐름"]
        direction LR
        F1["Supervisor\ndispatch_node"] -- "Send(StockState)" --> F2["StockAgent\n(인스턴스 N개)"]
        F2 -- "StockResult 반환" --> F3["Supervisor\naggregate_node"]
        F3 -- "stock_results 누적" --> F4["SupervisorState\n업데이트"]
    end

    SUP_STATE -.->|"dispatch 시 초기값 주입"| STOCK_STATE
    STOCK_STATE -.->|"완료 시 결과 반환"| SUP_STATE
```

---

## 7. ChromaDB ↔ SQLite 연결 구조

```mermaid
graph LR
    subgraph SQLite["🗄️ SQLite"]
        DB1["analyst_reports\nid=42"]
        DB2["dart_disclosures\nid=7"]
        DB3["news_articles\nid=155"]
        DB4["web_search_results\nid=3"]
    end

    subgraph ChromaDB["🔍 ChromaDB"]
        subgraph COL1["Collection: analyst_reports"]
            V1["doc_id: ar_42_p1\nmetadata:\n  source_id: 42\n  stock_code: 005930\n  report_date: 2026-04-01\n  page_num: 1"]
        end
        subgraph COL2["Collection: dart_disclosures"]
            V2["doc_id: dart_7\nmetadata:\n  source_id: 7\n  stock_code: 005930\n  disclosure_type: major_event"]
        end
        subgraph COL3["Collection: news_articles"]
            V3["doc_id: news_155\nmetadata:\n  source_id: 155\n  stock_code: 005930\n  published_at: 2026-04-08"]
        end
        subgraph COL4["Collection: web_search_results"]
            V4["doc_id: web_3\nmetadata:\n  source_id: 3\n  session_id: 11"]
        end
    end

    DB1 -- "source_id 연결" --> V1
    DB2 -- "source_id 연결" --> V2
    DB3 -- "source_id 연결" --> V3
    DB4 -- "source_id 연결" --> V4
```

---

## 8. 일별 자동화 파이프라인 타임라인

```mermaid
gantt
    title 일별 자동화 타임라인 — 멀티 에이전트 (18:00 시작, SEMI-AUTO)
    dateFormat HH:mm
    axisFormat %H:%M

    section CollectionAgent (순차)
    naver_report_node        :collect1, 18:00, 10m
    dart_node                :collect2, after collect1, 5m
    financial_node           :collect3, after collect2, 10m
    news_node + indexer_node :collect4, after collect3, 25m

    section StockAgent 병렬 (Send × 3)
    종목1 분석+질문생성       :agent1a, after collect4, 20m
    종목2 분석+질문생성       :agent2a, after collect4, 20m
    종목3 분석+질문생성       :agent3a, after collect4, 20m

    section HITL-1 (종목별 독립 대기)
    ⛔ 종목1 질문 검토        :crit, h1a, after agent1a, 30m
    ⛔ 종목2 질문 검토        :crit, h1b, after agent2a, 30m
    ⛔ 종목3 질문 검토        :crit, h1c, after agent3a, 30m

    section StockAgent 병렬 (검색+초안)
    종목1 검색+초안           :agent1b, after h1a, 15m
    종목2 검색+초안           :agent2b, after h1b, 15m
    종목3 검색+초안           :agent3b, after h1c, 15m

    section HITL-2 (종목별 독립 대기)
    ⛔ 종목1 초안 검토        :crit, h2a, after agent1b, 120m
    ⛔ 종목2 초안 검토        :crit, h2b, after agent2b, 120m
    ⛔ 종목3 초안 검토        :crit, h2c, after agent3b, 120m

    section aggregate + OutputAgent
    aggregate_node           :agg, after h2a, 2m
    OutputAgent (MD+PDF+PPT) :out, after agg, 15m

    section HITL-3 (Supervisor 최종 승인)
    ⛔ 전체 최종 승인         :crit, h3, after out, 240m
```
