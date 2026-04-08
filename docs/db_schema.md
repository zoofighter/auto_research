# DB 논리 설계서 - 주식 분석 AI 시스템

**작성일:** 2026-04-08  
**버전:** 1.0  
**기술 스택:** SQLite + SQLAlchemy ORM / ChromaDB (Vector DB)

---

## 1. 전체 구조 개요

```
┌─────────────────────────────────────────────┐
│            Primary DB (SQLite)              │
│                                             │
│  stocks ◄──────────────────────────────┐    │
│    │                                   │    │
│    ├── analyst_reports                 │    │
│    │       └── analyst_opinions        │    │
│    ├── financial_metrics               │    │
│    ├── dart_disclosures                │    │
│    ├── news_articles                   │    │
│    ├── analysis_sessions               │    │
│    │       └── web_search_results      │    │
│    └── generated_reports ─────────────┘    │
│              └── report_sources             │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│           Vector DB (ChromaDB)              │
│                                             │
│  Collection: analyst_reports  (PDF 청크)    │
│  Collection: dart_disclosures (공시 요약)   │
│  Collection: news_articles    (뉴스 요약)   │
│  Collection: web_search_results (검색 결과) │
│                                             │
│  ※ 각 문서의 metadata.source_id가          │
│     SQLite의 id와 연결됨                    │
└─────────────────────────────────────────────┘
```

---

## 2. Primary DB 테이블 설계

### 2.1 stocks — 종목 마스터

**목적:** 시스템 전체의 종목 기준 테이블. 모든 데이터의 FK 기준.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | INTEGER | PK | |
| stock_code | VARCHAR(20) | UNIQUE, NOT NULL | 종목코드 (예: 005930) |
| company_name | VARCHAR(100) | NOT NULL | 회사명 |
| sector | VARCHAR(100) | | 업종 |
| market_cap_category | VARCHAR(20) | | KOSPI / KOSDAQ / KONEX |
| is_watchlist | BOOLEAN | NOT NULL, DEFAULT false | 관심종목 여부 |
| created_at | DATETIME | DEFAULT now() | |
| updated_at | DATETIME | DEFAULT now() | |

**인덱스:** stock_code

---

### 2.2 analyst_reports — 애널리스트 리포트

**목적:** 네이버 금융에서 수집한 PDF 리포트 메타데이터 저장.  
`naver_research_downloader.py`의 출력이 이 테이블에 적재됨.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | INTEGER | PK | |
| stock_id | INTEGER | FK→stocks, NOT NULL | |
| title | VARCHAR(300) | NOT NULL | 리포트 제목 |
| firm_name | VARCHAR(100) | NOT NULL | 증권사명 |
| analyst_name | VARCHAR(100) | | 애널리스트명 |
| report_date | DATE | NOT NULL | 발행일 |
| pdf_url | VARCHAR(500) | NOT NULL | 원본 URL |
| pdf_path | VARCHAR(500) | | 로컬 저장 경로 |
| is_processed | BOOLEAN | DEFAULT false | ChromaDB 색인 완료 여부 |
| created_at | DATETIME | DEFAULT now() | |

**인덱스:** stock_id, report_date

---

### 2.3 analyst_opinions — 투자의견

**목적:** 리포트에서 LLM이 추출한 투자의견·목표주가. 시계열 추적으로 컨센서스 변화 분석.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | INTEGER | PK | |
| report_id | INTEGER | FK→analyst_reports, NOT NULL | |
| stock_id | INTEGER | FK→stocks, NOT NULL | 조회 편의용 반정규화 |
| opinion | VARCHAR(20) | | Buy / Hold / Sell / Neutral |
| price_target | FLOAT | | 목표주가 (원) |
| prev_price_target | FLOAT | | 직전 목표주가 (상향/하향 판단) |
| created_at | DATETIME | DEFAULT now() | |

**인덱스:** report_id, stock_id

---

### 2.4 financial_metrics — 재무 핵심 지표

**목적:** 네이버 주식에서 수집한 날짜별 재무 지표 스냅샷.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | INTEGER | PK | |
| stock_id | INTEGER | FK→stocks, NOT NULL | |
| metric_date | DATE | NOT NULL | 지표 기준일 |
| **[밸류에이션]** | | | |
| per | FLOAT | | PER |
| pbr | FLOAT | | PBR |
| psr | FLOAT | | PSR |
| ev_ebitda | FLOAT | | EV/EBITDA |
| **[수익성]** | | | |
| operating_margin | FLOAT | | 영업이익률 (%) |
| roe | FLOAT | | ROE (%) |
| roa | FLOAT | | ROA (%) |
| ebitda_margin | FLOAT | | EBITDA 마진 (%) |
| **[성장성]** | | | |
| revenue_yoy | FLOAT | | 매출 YoY (%) |
| op_income_yoy | FLOAT | | 영업이익 YoY (%) |
| eps_growth | FLOAT | | EPS 성장률 (%) |
| **[안정성]** | | | |
| debt_ratio | FLOAT | | 부채비율 (%) |
| current_ratio | FLOAT | | 유동비율 (%) |
| interest_coverage | FLOAT | | 이자보상배율 |
| **[시장 데이터]** | | | |
| market_cap | FLOAT | | 시가총액 (억원) |
| foreign_shareholding_pct | FLOAT | | 외국인 보유비율 (%) |
| net_institutional_buying | FLOAT | | 기관 순매수 (주) |
| created_at | DATETIME | DEFAULT now() | |

**제약:** UNIQUE(stock_id, metric_date)  
**인덱스:** stock_id, metric_date

---

### 2.5 dart_disclosures — DART 공시

**목적:** DART Open API로 수집한 공시 데이터. 주가 영향 이벤트(유상증자·CB 등) 감지.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | INTEGER | PK | |
| stock_id | INTEGER | FK→stocks, NOT NULL | |
| rcept_no | VARCHAR(20) | UNIQUE, NOT NULL | DART 접수번호 |
| disclosure_type | VARCHAR(50) | NOT NULL | business_report / quarterly / major_event / fair_disclosure |
| title | VARCHAR(300) | NOT NULL | 공시 제목 |
| corp_name | VARCHAR(100) | NOT NULL | 회사명 |
| rcept_dt | DATE | NOT NULL | 접수일 |
| url | VARCHAR(500) | | 공시 상세 URL |
| summary | TEXT | | LLM 요약 |
| is_major_event | BOOLEAN | DEFAULT false | 주가 영향 여부 |
| created_at | DATETIME | DEFAULT now() | |

**인덱스:** stock_id, rcept_dt, is_major_event

---

### 2.6 news_articles — 관심종목 뉴스

**목적:** 관심종목(is_watchlist=true) 대상 일별 뉴스 수집. LLM이 관련도 스코어링.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | INTEGER | PK | |
| stock_id | INTEGER | FK→stocks, NOT NULL | |
| headline | VARCHAR(500) | NOT NULL | 뉴스 제목 |
| url | VARCHAR(500) | NOT NULL | |
| source | VARCHAR(100) | | 언론사 |
| published_at | DATETIME | | 발행 시각 |
| relevance_score | FLOAT | | LLM 관련도 0.0~1.0 |
| summary | TEXT | | LLM 요약 |
| created_at | DATETIME | DEFAULT now() | |

**인덱스:** stock_id, published_at

---

### 2.7 analysis_sessions — LangGraph 워크플로우 세션

**목적:** 분석 실행 이력 관리. 반복(iteration) 횟수, 생성된 질문, 상태 추적.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | INTEGER | PK | |
| stock_id | INTEGER | FK→stocks, NOT NULL | |
| started_at | DATETIME | DEFAULT now() | |
| completed_at | DATETIME | | |
| status | VARCHAR(20) | DEFAULT 'running' | running / completed / failed |
| iteration_count | INTEGER | DEFAULT 0 | 자율 질문→검색 반복 횟수 |
| generated_questions | TEXT | | JSON 배열 (질문 리스트) |
| created_at | DATETIME | DEFAULT now() | |

**인덱스:** stock_id, status

---

### 2.8 web_search_results — 웹 검색 결과

**목적:** 자율 질문 기반으로 실행된 웹 검색 결과 저장. RAG 추가 색인 대상.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | INTEGER | PK | |
| session_id | INTEGER | FK→analysis_sessions, NOT NULL | |
| question | TEXT | NOT NULL | 생성된 자율 질문 |
| query | VARCHAR(500) | NOT NULL | 실제 검색어 |
| result_url | VARCHAR(500) | | |
| result_snippet | TEXT | | 검색 결과 스니펫 |
| created_at | DATETIME | DEFAULT now() | |

**인덱스:** session_id

---

### 2.9 generated_reports — 최종 보고서

**목적:** AI가 생성한 최종 분석 보고서 및 PPT 경로 저장.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | INTEGER | PK | |
| stock_id | INTEGER | FK→stocks, NOT NULL | |
| session_id | INTEGER | FK→analysis_sessions, NOT NULL | |
| report_date | DATE | NOT NULL | 보고서 기준일 |
| executive_summary | TEXT | | Executive Summary (3줄) |
| report_md_path | VARCHAR(500) | | Markdown 파일 경로 |
| report_pdf_path | VARCHAR(500) | | PDF 파일 경로 |
| ppt_path | VARCHAR(500) | | PPT 파일 경로 |
| quality_score | FLOAT | | LLM 자체 평가 0.0~1.0 |
| created_at | DATETIME | DEFAULT now() | |

**인덱스:** stock_id, report_date

---

### 2.10 report_sources — 출처 추적 (Audit Trail)

**목적:** 보고서의 각 근거가 어떤 원본 문서에서 왔는지 추적. 환각 방지.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | INTEGER | PK | |
| generated_report_id | INTEGER | FK→generated_reports, NOT NULL | |
| source_type | VARCHAR(30) | NOT NULL | analyst_report / dart / news / web |
| source_id | INTEGER | | 해당 테이블의 id |
| excerpt | TEXT | | 인용 구절 |
| created_at | DATETIME | DEFAULT now() | |

**인덱스:** generated_report_id

---

## 3. ERD (관계 다이어그램)

```
stocks (1) ─────────────────────────────────── (N) analyst_reports
   │                                                      │
   │                                              (N) analyst_opinions
   │
   ├── (N) financial_metrics
   ├── (N) dart_disclosures
   ├── (N) news_articles
   │
   ├── (N) analysis_sessions (1) ─── (N) web_search_results
   │
   └── (N) generated_reports (1) ─── (N) report_sources
              │
              └── FK→ analysis_sessions
```

---

## 4. Vector DB 설계 (ChromaDB)

SQLite와 별도 운영. 각 문서의 `metadata.source_id`로 SQLite 레코드와 연결.

### 컬렉션 목록

| 컬렉션명 | 색인 대상 | 청크 단위 | 메타데이터 |
|---------|---------|---------|----------|
| `analyst_reports` | PDF 본문 | 페이지 단위 (~500 토큰) | stock_code, report_id, firm_name, report_date, page_num |
| `dart_disclosures` | 공시 요약 | 문서 단위 | stock_code, disclosure_id, disclosure_type, rcept_dt |
| `news_articles` | 뉴스 요약 | 문서 단위 | stock_code, news_id, source, published_at |
| `web_search_results` | 검색 스니펫 | 문서 단위 | session_id, question, result_url |

### SQLite ↔ ChromaDB 연결 규칙

```
ChromaDB document id 규칙:
  analyst_reports   → "ar_{report_id}_p{page_num}"
  dart_disclosures  → "dart_{disclosure_id}"
  news_articles     → "news_{news_id}"
  web_search_results → "web_{result_id}"

metadata.source_id = SQLite 해당 테이블의 id
```

### RAG 쿼리 시 필터 예시

```
analyst_reports 컬렉션에서 특정 종목만 검색:
  where = {"stock_code": "005930"}

최근 1년 리포트만 검색:
  where = {"report_date": {"$gte": "2025-04-08"}}
```

---

## 5. 데이터 흐름 요약

```
[수집 단계]
  naver_research_downloader.py
    → analyst_reports 테이블 적재
    → PDF 청크 → ChromaDB(analyst_reports) 색인
    → is_processed = true 업데이트

  DART API 수집기
    → dart_disclosures 테이블 적재
    → 요약 → ChromaDB(dart_disclosures) 색인

  뉴스 수집기 (관심종목 기준)
    → news_articles 테이블 적재
    → 요약·스코어링 → ChromaDB(news_articles) 색인

  재무 지표 수집기
    → financial_metrics 테이블 적재

[분석 단계 — LangGraph]
  analysis_sessions 생성 (status=running)
    → RAG 조회 (ChromaDB 4개 컬렉션)
    → 자율 질문 생성 → generated_questions 저장
    → 웹 검색 → web_search_results 적재
                → ChromaDB(web_search_results) 색인
    → 보고서 초안 작성 → 품질 평가
    → quality_score < 임계값이면 iteration_count++ 후 재반복
    → 완료 시 status=completed

[출력 단계]
  generated_reports 적재 (md/pdf/ppt 경로)
  report_sources 적재 (출처 추적)
```
