# 시스템 다이어그램

**작성일:** 2026-04-08

---

## 1. 전체 시스템 아키텍처

```mermaid
graph TB
    subgraph Sources["📥 데이터 소스"]
        S1[네이버 금융\n리포트 PDF]
        S2[DART\nOpen API]
        S3[네이버 주식\n재무 지표]
        S4[네이버 뉴스]
    end

    subgraph Collectors["🔄 Phase 2: 수집기 (collectors/)"]
        C1[naver_report.py]
        C2[dart_api.py]
        C3[naver_financial.py]
        C4[news_collector.py]
    end

    subgraph PrimaryDB["🗄️ Primary DB (SQLite)"]
        DB1[(analyst_reports)]
        DB2[(dart_disclosures)]
        DB3[(financial_metrics)]
        DB4[(news_articles)]
        DB5[(analysis_sessions)]
        DB6[(generated_reports)]
    end

    subgraph RAG["🔍 Phase 3: RAG 파이프라인 (vector_db/)"]
        R1[indexer.py\nPDF 청크 분할]
        R2[(ChromaDB\n4개 컬렉션)]
        R3[retriever.py\n유사도 검색]
    end

    subgraph Agent["🤖 Phase 4: LangGraph 에이전트 (agents/)"]
        A1[graph.py\n워크플로우 실행]
        LLM[🦙 Qwen\nOllama 로컬]
    end

    subgraph Output["📄 Phase 5: 보고서 생성 (reporters/)"]
        O1[markdown_writer.py]
        O2[pdf_exporter.py]
        O3[ppt_builder.py]
    end

    subgraph Final["📦 최종 출력물"]
        F1[📝 Report.md]
        F2[📄 Report.pdf]
        F3[📊 Report.pptx]
    end

    S1 --> C1
    S2 --> C2
    S3 --> C3
    S4 --> C4

    C1 --> DB1
    C2 --> DB2
    C3 --> DB3
    C4 --> DB4

    DB1 --> R1
    DB2 --> R1
    DB4 --> R1
    R1 --> R2
    R2 --> R3

    R3 --> A1
    DB3 --> A1
    A1 <--> LLM
    A1 --> DB5

    DB5 --> O1
    DB3 --> O1
    O1 --> F1
    O1 --> O2
    O1 --> O3
    O2 --> F2
    O3 --> F3
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

## 4. LangGraph 워크플로우 — 전체 상태 그래프

```mermaid
stateDiagram-v2
    [*] --> collect_node : 세션 시작\n(stock_code, session_id)

    collect_node --> analyze_node : RAG 초기 문서 수집 완료\n(analyst_reports + dart + news)

    analyze_node --> question_node : 분석 메모 생성 완료\n(투자의견·목표주가·리스크 추출)

    question_node --> search_node : 자율 질문 3~5개 생성\n(분석 공백 탐지 기반)

    search_node --> synthesize_node : 웹 검색 완료\n(ChromaDB 추가 색인)

    synthesize_node --> evaluate_node : 보고서 초안 작성 완료\n(전체 문서 통합)

    evaluate_node --> output_node : quality_score ≥ 0.7\n또는 iteration ≥ 3

    evaluate_node --> question_node : quality_score < 0.7\n& iteration < 3\n(iteration++)

    output_node --> [*] : 보고서·PPT 저장\nsession status = completed
```

---

## 5. LangGraph 노드별 상세 처리 흐름

```mermaid
flowchart TD
    START([▶ START\nstock_code 입력]) --> INIT

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
        Q4["generated_questions\n→ analysis_sessions 업데이트"]
    end

    QUESTION --> SEARCH

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

    SYNTHESIZE --> EVALUATE

    subgraph EVALUATE["⚖️ evaluate_node — 품질 평가"]
        E1["근거 충분성 평가\n주장별 출처 존재 여부\n(0 ~ 0.3점)"] --> E2
        E2["균형성 평가\n긍정/부정 양면 포함\n(0 ~ 0.3점)"] --> E3
        E3["구체성 평가\n수치·날짜 포함 여부\n(0 ~ 0.2점)"] --> E4
        E4["논리성 평가\nSummary ↔ 본문 일치\n(0 ~ 0.2점)"] --> E5
        E5["quality_score 합산\n0.0 ~ 1.0"]
    end

    EVALUATE --> BRANCH{{"🔀 분기 판단\nquality_score ≥ 0.7?\n또는 iteration ≥ 3?"}}

    BRANCH -- "YES\n(통과 또는 강제 종료)" --> OUTPUT

    BRANCH -- "NO\niteration++" --> QUESTION

    subgraph OUTPUT["💾 output_node — 최종 저장"]
        O1["generated_reports INSERT\n(md/pdf/ppt 경로, quality_score)"] --> O2
        O2["report_sources INSERT\n(출처 audit trail)"] --> O3
        O3["analysis_sessions 업데이트\nstatus = completed\ncompleted_at = now()"]
    end

    OUTPUT --> END([⏹ END\n보고서 생성 완료])

    style BRANCH fill:#fff3cd,stroke:#ffc107
    style EVALUATE fill:#f8d7da,stroke:#dc3545
    style OUTPUT fill:#d1e7dd,stroke:#198754
    style START fill:#cfe2ff,stroke:#0d6efd
    style END fill:#cfe2ff,stroke:#0d6efd
```

---

## 6. LangGraph 상태(State) 전이 상세

```mermaid
flowchart LR
    subgraph State["📋 AgentState 스키마"]
        direction TB
        ST1["stock_code: str"]
        ST2["company_name: str"]
        ST3["session_id: int"]
        ST4["collected_docs: list[dict]\n(RAG 검색 결과 누적)"]
        ST5["analysis_notes: str\n(중간 분석 메모)"]
        ST6["generated_questions: list[str]"]
        ST7["search_results: list[dict]"]
        ST8["report_draft: str"]
        ST9["quality_score: float"]
        ST10["iteration: int\n(최대 3)"]
        ST11["status: str\nrunning/completed/failed"]
    end

    subgraph Mutations["🔄 노드별 State 변경"]
        direction TB
        M1["collect_node\n→ collected_docs 채움"]
        M2["analyze_node\n→ analysis_notes 채움"]
        M3["question_node\n→ generated_questions 채움"]
        M4["search_node\n→ search_results 추가\n→ collected_docs 확장"]
        M5["synthesize_node\n→ report_draft 채움"]
        M6["evaluate_node\n→ quality_score 산정\n→ iteration 증가"]
        M7["output_node\n→ status = completed"]
    end

    State -.-> Mutations
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
    title 일별 자동화 실행 타임라인 (18:00 시작)
    dateFormat HH:mm
    axisFormat %H:%M

    section 데이터 수집
    네이버 리포트 수집       :collect1, 18:00, 10m
    DART 공시 수집           :collect2, after collect1, 5m
    재무 지표 수집           :collect3, after collect2, 10m
    뉴스 수집 + 스코어링     :collect4, after collect3, 15m

    section RAG 색인
    ChromaDB 신규 색인       :index, after collect4, 10m

    section AI 분석 (종목별)
    종목 1 LangGraph 실행    :agent1, after index, 20m
    종목 2 LangGraph 실행    :agent2, after index, 20m
    종목 3 LangGraph 실행    :agent3, after index, 20m

    section 보고서 생성
    MD 보고서 생성           :report1, after agent1, 5m
    PDF 변환                 :report2, after report1, 3m
    PPT 생성                 :report3, after report2, 5m
```
