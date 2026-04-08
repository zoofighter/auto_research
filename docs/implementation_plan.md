# 구현 상세 계획 및 전략

**작성일:** 2026-04-08  
**버전:** 1.0

---

## 1. 전체 구현 전략

### 핵심 원칙
- **점진적 구축:** 데이터 수집 → 저장 → 분석 → 출력 순서로 단계별 검증
- **기존 코드 재활용:** `naver_research_downloader.py`를 Phase 1의 기반으로 활용
- **로컬 우선:** 외부 API 의존 최소화, 로컬 LLM(Qwen)과 로컬 DB 중심 설계
- **모듈 독립성:** 각 수집기가 독립 실행 가능하게 설계하여 장애 격리

### 구현 단계 개요

```
Phase 1: 기반 인프라       (DB + 설정 + 공통 유틸)
Phase 2: 데이터 수집기     (5개 소스별 수집 모듈)
Phase 3: RAG 파이프라인    (ChromaDB 색인 + 검색)
Phase 4: LangGraph 에이전트 (워크플로우 + 자율 질문)
Phase 5: 보고서 생성기     (Report MD/PDF + PPT)
Phase 6: 스케줄러          (일괄 자동화)
```

---

## 2. 프로젝트 디렉터리 구조

```
a_0408_report/
│
├── config.py                    # 전역 설정 (API 키, 경로, 임계값)
├── naver_research_downloader.py # [기존] Phase 2에서 래핑하여 재활용
│
├── db/                          # Phase 1
│   ├── base.py                  # SQLAlchemy engine, session, Base
│   └── models/
│       ├── stock.py
│       ├── report.py
│       ├── financial.py
│       ├── dart.py
│       ├── news.py
│       ├── analysis.py
│       └── output.py
│
├── collectors/                  # Phase 2 — 데이터 수집기
│   ├── naver_report.py          # 기존 downloader 래핑 + DB 적재
│   ├── dart_api.py              # DART Open API 수집
│   ├── naver_financial.py       # 네이버 재무 지표 스크래핑
│   ├── news_collector.py        # 관심종목 뉴스 수집
│   └── stock_manager.py         # 종목 마스터 관리 (watchlist 추가/제거)
│
├── vector_db/                   # Phase 3 — RAG
│   ├── chroma_client.py         # ChromaDB 연결 및 컬렉션 초기화
│   ├── indexer.py               # SQLite → ChromaDB 색인 파이프라인
│   └── retriever.py             # RAG 검색 인터페이스 (LangChain 연동)
│
├── agents/                      # Phase 4 — LangGraph 워크플로우
│   ├── graph.py                 # LangGraph 상태 그래프 정의
│   ├── nodes/
│   │   ├── analyst.py           # 문서 분석 노드
│   │   ├── questioner.py        # 자율 질문 생성 노드
│   │   ├── searcher.py          # 웹 검색 실행 노드
│   │   └── evaluator.py         # 품질 평가 및 루프 판단 노드
│   └── state.py                 # LangGraph 상태 스키마
│
├── reporters/                   # Phase 5 — 보고서 생성
│   ├── markdown_writer.py       # 분석 보고서 Markdown 생성
│   ├── pdf_exporter.py          # Markdown → PDF 변환
│   └── ppt_builder.py           # PowerPoint 생성
│
├── scheduler/                   # Phase 6 — 자동화
│   └── daily_runner.py          # 일별 전체 파이프라인 실행
│
├── data/                        # 런타임 생성 (git ignore)
│   ├── stock_analysis.db        # SQLite DB 파일
│   └── chroma/                  # ChromaDB 저장소
│
├── reports/                     # 출력물 (git ignore)
│   └── YYYY-MM-DD/
│       ├── {종목코드}_report.md
│       ├── {종목코드}_report.pdf
│       └── {종목코드}_report.pptx
│
└── docs/
    ├── human.md
    ├── requirements_definition.md
    ├── db_schema.md
    └── implementation_plan.md   # 이 파일
```

---

## 3. Phase별 상세 구현 계획

---

### Phase 1: 기반 인프라

**목표:** DB 스키마 생성, 전역 설정, 공통 유틸 구축

#### 1-1. `config.py` — 전역 설정

```
관리 항목:
  - DB 경로 (data/stock_analysis.db)
  - ChromaDB 저장 경로 (data/chroma/)
  - 로컬 LLM 엔드포인트 (Ollama: http://localhost:11434)
  - Qwen 모델명 (예: qwen2.5:14b)
  - DART API 키
  - 임베딩 모델명 (예: nomic-embed-text)
  - 품질 점수 임계값 (기본 0.7)
  - 최대 반복 횟수 (기본 3)
  - 관심종목 최대 수 (기본 10개)
```

#### 1-2. DB 초기화

```
실행 방법: python -c "from db.base import init_db; init_db()"

생성 테이블: stocks, analyst_reports, analyst_opinions,
            financial_metrics, dart_disclosures, news_articles,
            analysis_sessions, web_search_results,
            generated_reports, report_sources
```

#### 검증 포인트
- `data/stock_analysis.db` 파일 생성 확인
- 10개 테이블 존재 확인
- FK 제약 정상 동작 확인

---

### Phase 2: 데이터 수집기

**목표:** 5개 소스에서 데이터 수집 후 SQLite 적재

#### 2-1. `collectors/naver_report.py` — 리포트 수집기

```
기반: 기존 naver_research_downloader.py 재활용

추가 기능:
  1. fetch_report_list() 결과를 analyst_reports 테이블에 INSERT
  2. stock_code 매핑: company_name → stocks 테이블 조회 후 stock_id 획득
     (없으면 stocks 테이블에 신규 INSERT)
  3. 중복 방지: pdf_url 기준 이미 수집된 리포트 스킵
  4. is_processed=false로 초기 적재 (Phase 3에서 ChromaDB 색인 후 true로 업데이트)
  5. 1년치 과거 데이터: today_only=False, max_pages=50 으로 대량 수집 지원

실행 모드:
  - 일별 신규: today_only=True (Phase 6 스케줄러)
  - 초기 구축: today_only=False, max_pages=50 (최초 1회)
```

#### 2-2. `collectors/dart_api.py` — DART 공시 수집기

```
API: https://opendart.fss.or.kr/api/list.json

수집 흐름:
  1. stocks 테이블의 is_watchlist=true 종목 조회
  2. 각 종목의 stock_code로 DART corp_code 매핑
     (DART 기업코드 파일 다운로드: corpCode.xml)
  3. DART API 호출: 공시 목록 조회 (최근 30일)
  4. rcept_no 중복 체크 후 dart_disclosures 테이블 INSERT
  5. 주요 공시 판별 (is_major_event):
     - 유상증자, CB발행, 주식매수선택권, 배당, 최대주주 변경 등
     - disclosure_type='major_event' 이거나 제목 키워드 매칭

중복 방지: rcept_no UNIQUE 제약 → INSERT OR IGNORE
```

#### 2-3. `collectors/naver_financial.py` — 재무 지표 수집기

```
대상 URL 패턴:
  https://finance.naver.com/item/main.naver?code={stock_code}

스크래핑 대상:
  - 기본 정보: 시가총액, 외국인 비율
  - 투자 지표: PER, PBR, ROE
  - 재무 요약 테이블: 영업이익률, 부채비율 등

수집 흐름:
  1. is_watchlist=true 종목 순회
  2. 오늘 날짜 기준 financial_metrics 레코드 이미 있으면 스킵
  3. 스크래핑 후 financial_metrics INSERT

한계 및 보완:
  - 네이버는 일부 지표만 노출 → PSR, EV/EBITDA는 DART 재무제표로 직접 계산
  - 계산 불가 항목은 NULL로 저장
```

#### 2-4. `collectors/news_collector.py` — 뉴스 수집기

```
대상: 네이버 뉴스 종목 관련 기사
URL 패턴:
  https://finance.naver.com/item/news_news.naver?code={stock_code}

수집 흐름:
  1. is_watchlist=true 종목 순회 (최대 10개)
  2. 오늘 날짜 뉴스 최대 20건 수집
  3. LLM(Qwen)으로 relevance_score 산정:
     - 프롬프트: "이 뉴스가 {company_name} 주가에 미치는 영향도를 0~1로 평가"
  4. relevance_score >= 0.5인 뉴스만 summary 생성 후 INSERT
  5. 일별 종목당 최대 5건 저장 (score 상위 5건)
```

#### 2-5. `collectors/stock_manager.py` — 종목 마스터 관리

```
기능:
  - 종목 추가: stock_code + company_name → stocks 테이블 INSERT
  - 관심종목 설정: is_watchlist 토글
  - 섹터 분류: 수동 입력 또는 네이버 업종 자동 조회
  - 종목 목록 조회: watchlist 필터링

CLI 인터페이스:
  python collectors/stock_manager.py add 005930 삼성전자
  python collectors/stock_manager.py watchlist 005930
  python collectors/stock_manager.py list
```

---

### Phase 3: RAG 파이프라인

**목표:** 수집된 데이터를 ChromaDB에 색인하여 LLM이 검색 가능하게 구성

#### 3-1. `vector_db/chroma_client.py` — ChromaDB 연결

```
설정:
  - persist_directory: data/chroma/
  - embedding_function: OllamaEmbeddings(model="nomic-embed-text")
    (Ollama 로컬 임베딩, 외부 API 불필요)

4개 컬렉션 초기화:
  - analyst_reports
  - dart_disclosures
  - news_articles
  - web_search_results
```

#### 3-2. `vector_db/indexer.py` — SQLite → ChromaDB 색인

```
analyst_reports 색인:
  1. is_processed=false인 레코드 조회
  2. pdf_path가 있는 경우 PDF 로드 (PyPDFLoader)
  3. 페이지 단위 청크 분할 (RecursiveCharacterTextSplitter, chunk=500)
  4. ChromaDB에 upsert (doc_id: "ar_{report_id}_p{page_num}")
  5. is_processed=true 업데이트

dart_disclosures 색인:
  - summary가 있는 레코드 → 문서 단위로 upsert
  - doc_id: "dart_{disclosure_id}"

news_articles 색인:
  - summary가 있는 레코드 → 문서 단위로 upsert
  - doc_id: "news_{news_id}"

web_search_results 색인:
  - result_snippet → 문서 단위로 upsert
  - doc_id: "web_{result_id}"
```

#### 3-3. `vector_db/retriever.py` — RAG 검색 인터페이스

```
LangChain MultiVectorRetriever 패턴 적용

검색 메서드:
  search(query, stock_code, top_k=5, collections=["all"])
    - stock_code 필터로 해당 종목 문서만 검색
    - collections 파라미터로 특정 소스만 검색 가능
    - 결과에 출처(source_type, source_id) 포함

반환 형식:
  [
    {
      "content": "...",
      "source_type": "analyst_report",
      "source_id": 42,
      "metadata": { "firm_name": "...", "report_date": "..." }
    },
    ...
  ]
```

---

### Phase 4: LangGraph 에이전트

**목표:** 자율 분석 워크플로우 구현 — 분석 → 질문 생성 → 검색 → 재분석 → 평가 루프

#### 4-1. `agents/state.py` — 상태 스키마

```
LangGraph State 구성:
  - stock_code: str
  - company_name: str
  - session_id: int               # analysis_sessions FK
  - collected_docs: list[dict]    # RAG 검색 결과 누적
  - analysis_notes: str           # 중간 분석 메모
  - generated_questions: list[str]
  - search_results: list[dict]
  - report_draft: str
  - quality_score: float
  - iteration: int
  - status: str                   # running / completed / failed
```

#### 4-2. `agents/graph.py` — LangGraph 워크플로우

```
노드 구성 및 실행 순서:

[START]
  ↓
[collect_node]     : RAG로 초기 문서 수집 (analyst_reports + dart + news)
  ↓
[analyze_node]     : 수집 문서 종합 → analysis_notes 생성
  ↓
[question_node]    : 분석 공백 탐지 → 자율 질문 3~5개 생성
  ↓
[search_node]      : 질문별 웹 검색 → web_search_results 적재 + ChromaDB 색인
  ↓
[synthesize_node]  : 전체 문서 + 검색 결과 통합 → report_draft 작성
  ↓
[evaluate_node]    : 보고서 품질 평가 → quality_score 산정
  ↓
[조건 분기]
  quality_score >= 0.7 or iteration >= 3
    → YES → [output_node] → [END]
    → NO  → iteration++ → [question_node] (루프)

조건 분기 구현: LangGraph의 conditional_edges 사용
```

#### 4-3. 각 노드 상세 로직

**analyze_node (문서 분석)**
```
입력: collected_docs
처리:
  - 투자의견 변화 추적 (Buy→Hold 등)
  - 목표주가 트렌드 (상향/하향 횟수)
  - 핵심 리스크 키워드 추출
  - 재무 지표 이상치 탐지
출력: analysis_notes (구조화된 분석 메모)
```

**question_node (자율 질문 생성)**
```
입력: analysis_notes
프롬프트 전략:
  "다음 분석에서 불확실하거나 추가 확인이 필요한 사항을
   구체적인 검색 질문 형태로 3~5개 생성하라"

예시 생성 질문:
  - "{company_name}의 최근 3개월 외국인 순매도 원인은?"
  - "{company_name} vs {competitor} PER 프리미엄 이유는?"
  - "{company_name} {사업분야} 시장 점유율 변화 2025~2026"
```

**evaluate_node (품질 평가)**
```
평가 기준 (LLM 자체 평가):
  - 근거 충분성: 주장마다 출처 문서가 있는가 (0~0.3)
  - 균형성: 긍정/부정 양면을 모두 다루는가 (0~0.3)
  - 구체성: 수치와 날짜가 포함되는가 (0~0.2)
  - 논리성: Executive Summary와 본문이 일치하는가 (0~0.2)

합산 quality_score 0.0~1.0
임계값 0.7 미달 시 루프 재진입
```

---

### Phase 5: 보고서 생성기

**목표:** LangGraph 최종 draft를 형식화된 Report(MD/PDF) + PPT로 변환

#### 5-1. `reporters/markdown_writer.py`

```
입력: report_draft (LangGraph 출력), session_id, stock_code
출력: reports/YYYY-MM-DD/{stock_code}_report.md

문서 구조 (요건정의서 기준):
  1. Executive Summary
  2. 기업 개요
  3. 재무 분석 (financial_metrics 테이블 데이터 삽입)
  4. 애널리스트 컨센서스 (analyst_opinions 집계)
  5. 리스크 요인
  6. 결론 및 투자 포인트
  7. 출처 목록 (report_sources 테이블 기반)

재무 데이터 삽입:
  - financial_metrics에서 최근 1년치 조회
  - Markdown 테이블 형식으로 자동 생성
```

#### 5-2. `reporters/pdf_exporter.py`

```
변환 도구: md → PDF
  옵션 A: pandoc CLI 사용 (로컬 설치 필요)
  옵션 B: weasyprint Python 라이브러리

입력: .md 파일 경로
출력: 동일 디렉터리에 .pdf 생성
```

#### 5-3. `reporters/ppt_builder.py`

```
도구: python-pptx

슬라이드 구성 (9장):
  Slide 1: 표지 (종목명, 날짜, 투자의견 배지)
  Slide 2: Executive Summary (불릿 3개)
  Slide 3: 기업 개요 (사업 구조 텍스트)
  Slide 4: 사업 모델 & 경쟁 포지션
  Slide 5: 재무 KPI 테이블 (financial_metrics)
  Slide 6: 주요 지표 트렌드 (텍스트 기반, 차트는 선택)
  Slide 7: 애널리스트 컨센서스 요약
  Slide 8: 리스크 요인 (단기 / 중장기 구분)
  Slide 9: 결론 & 투자 포인트

데이터 주입:
  - Markdown 파싱 후 섹션별 텍스트 추출
  - financial_metrics 테이블 직접 조회하여 슬라이드 5~6 생성
```

---

### Phase 6: 스케줄러 (일괄 자동화)

**목표:** 매일 장 마감 후 전체 파이프라인 자동 실행

#### 6-1. `scheduler/daily_runner.py` — 실행 순서

```
실행 시각: 매일 18:00 (장 마감 후)

Step 1. 리포트 수집
  → naver_report.py (today_only=True)
  → dart_api.py (오늘 공시)
  → naver_financial.py (오늘 재무 지표)
  → news_collector.py (오늘 뉴스)

Step 2. ChromaDB 색인
  → indexer.py (is_processed=false 신규 문서만)

Step 3. 분석 에이전트 실행
  → is_watchlist=true 종목 순회
  → 각 종목별 LangGraph 실행
  → analysis_sessions 생성 및 완료 업데이트

Step 4. 보고서 생성
  → markdown_writer.py
  → pdf_exporter.py
  → ppt_builder.py

Step 5. 로그 기록
  → 실행 결과 요약 출력 (성공 종목 수, 실패 종목 목록)
```

#### 6-2. 스케줄러 설정 옵션

```
옵션 A: cron (macOS launchd)
  → 운영 환경에 적합, 시스템 재시작 후 자동 재개

옵션 B: Python APScheduler
  → 코드 내에서 스케줄 관리, 별도 시스템 설정 불필요

옵션 C: 수동 실행
  → python scheduler/daily_runner.py
  → 초기 개발·테스트 단계에서 권장
```

---

## 4. 기술 스택 확정

| 영역 | 기술 | 버전 기준 |
|------|------|---------|
| 언어 | Python | 3.11+ |
| Primary DB | SQLite + SQLAlchemy | SQLAlchemy 2.0 |
| DB 마이그레이션 | Alembic | 1.13+ |
| Vector DB | ChromaDB | 0.5+ |
| LLM 프레임워크 | LangChain + LangGraph | LangChain 0.3+ |
| 로컬 LLM | Qwen (via Ollama) | qwen2.5:14b 권장 |
| 임베딩 | nomic-embed-text (via Ollama) | 로컬 실행 |
| 웹 스크래핑 | requests + BeautifulSoup4 | 기존 코드 재활용 |
| PDF 파싱 | PyPDFLoader (LangChain) | |
| PDF 생성 | pandoc or weasyprint | |
| PPT 생성 | python-pptx | |
| 스케줄러 | APScheduler (선택) | |

---

## 5. 의존성 및 연동 흐름

```
[외부 의존성]
  네이버 금융 (스크래핑)  ──→ collectors/naver_report.py
                                        collectors/naver_financial.py
                                        collectors/news_collector.py
  DART Open API           ──→ collectors/dart_api.py
  Ollama (로컬 서버)       ──→ agents/*.py (LLM 추론)
                                        vector_db/chroma_client.py (임베딩)
  웹 검색 (선택)           ──→ agents/nodes/searcher.py
    - DuckDuckGo Search (무료, LangChain 내장)
    - 또는 SerpAPI (유료, 더 정확)

[내부 데이터 흐름]
  collectors/* → SQLite (analysts_reports, dart_disclosures, ...)
  indexer.py   → SQLite(is_processed) + ChromaDB
  agents/*     → ChromaDB(검색) + SQLite(세션 저장)
  reporters/*  → SQLite(데이터 조회) + 파일시스템(출력)
```

---

## 6. 리스크 및 대응 전략

| 리스크 | 발생 가능성 | 대응 |
|--------|----------|------|
| 네이버 스크래핑 차단 | 중 | User-Agent 로테이션, 요청 간격 2~3초로 증가, 차단 시 selenium 대안 |
| DART API 한도 초과 | 낮 | 일일 10,000건 무료 한도 내 운영, 초과 시 다음날 재시도 |
| Qwen 응답 품질 부족 | 중 | 프롬프트 튜닝, 필요 시 더 큰 모델(qwen2.5:32b)로 교체 |
| PDF 파싱 오류 | 중 | 파싱 실패 리포트는 `is_processed=error`로 마킹 후 스킵, 별도 재처리 큐 |
| ChromaDB 색인 누락 | 낮 | `is_processed` 플래그로 멱등성 보장, 언제든 재색인 가능 |
| 보고서 품질 임계값 미달 루프 | 중 | `iteration >= 3` 강제 종료 조건으로 무한 루프 방지 |

---

## 7. 구현 우선순위 (단계별 체크리스트)

### Phase 1 완료 기준
- [ ] `config.py` 작성
- [ ] `db/base.py` + 모든 모델 작성
- [ ] `init_db()` 실행 시 10개 테이블 생성 확인

### Phase 2 완료 기준
- [ ] `naver_report.py` 실행 → analyst_reports 테이블에 데이터 적재 확인
- [ ] `dart_api.py` 실행 → dart_disclosures 테이블에 데이터 적재 확인
- [ ] `naver_financial.py` 실행 → financial_metrics 테이블에 데이터 적재 확인
- [ ] `news_collector.py` 실행 → news_articles 테이블에 데이터 적재 확인
- [ ] `stock_manager.py add` 명령으로 관심종목 등록 확인

### Phase 3 완료 기준
- [ ] ChromaDB 4개 컬렉션 생성 확인
- [ ] `indexer.py` 실행 후 `is_processed=true` 업데이트 확인
- [ ] `retriever.py` 검색 결과에 출처 메타데이터 포함 확인

### Phase 4 완료 기준
- [ ] LangGraph 그래프 단일 종목으로 end-to-end 실행 확인
- [ ] `analysis_sessions` 테이블에 세션 기록 확인
- [ ] `web_search_results` 테이블에 검색 결과 적재 확인
- [ ] quality_score < 0.7 시 루프 재진입 동작 확인
- [ ] iteration >= 3 시 강제 종료 동작 확인

### Phase 5 완료 기준
- [ ] `reports/YYYY-MM-DD/` 디렉터리에 .md 파일 생성 확인
- [ ] .md → .pdf 변환 확인
- [ ] .pptx 9장 슬라이드 생성 확인
- [ ] `report_sources` 테이블에 출처 기록 확인

### Phase 6 완료 기준
- [ ] `daily_runner.py` 단독 실행으로 전체 파이프라인 완주 확인
- [ ] 관심종목 3개 이상에서 보고서 동시 생성 확인
