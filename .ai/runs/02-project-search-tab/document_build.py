import sys
import os

# docx_helper 경로 추가
sys.path.insert(0, ".ai/templates")
from docx_helper import (
    create_doc, add_h1, add_h2, add_paragraph,
    add_bullet, add_code_block, add_table
)

doc = create_doc()

# ── 1. 개요 ──────────────────────────────────────────────────────────────────
add_h1(doc, "1. 개요")
add_table(doc,
    headers=["항목", "내용"],
    rows=[
        ["기능 이름", "02-project-search-tab"],
        ["기능 목적", "기존 시장 대시보드를 보존하면서, 한국/미국 주식 및 ETF 종목의 통합 검색, 자동완성, 상세 시세 및 차트 정보를 제공하는 신규 탭을 추가한다."],
        ["최종 판정", "PASS"],
        ["최종 완성 일시", "2026-06-04"],
    ]
)

# ── 2. 사용 방법 ──────────────────────────────────────────────────────────────
add_h1(doc, "2. 사용 방법")
add_h2(doc, "백엔드 API 엔드포인트")
add_bullet(doc, "GET /api/search/autocomplete : 검색어 입력에 따른 실시간 종목 자동완성 목록 반환 (최대 10개 후보)")
add_bullet(doc, "GET /api/stocks/{symbol}/detail : 선택한 종목의 상세 시세 데이터 및 메타데이터 반환")
add_bullet(doc, "GET /api/stocks/{symbol}/chart : 선택한 종목의 차트 데이터 반환 (기간 파라미터 1m, 3m, 6m, 1y 지원)")

add_h2(doc, "파라미터 정의")
add_table(doc,
    headers=["API", "파라미터 명", "타입", "설명"],
    rows=[
        ["/api/search/autocomplete", "q", "string", "최소 2자 이상의 검색어 (한글/영어 티커)"],
        ["/api/search/autocomplete", "category", "string", "검색 시장 범주 (kr_stock, kr_etf, us_stock, us_etf)"],
        ["/api/stocks/{symbol}/detail", "symbol", "string", "종목 코드 또는 티커"],
        ["/api/stocks/{symbol}/detail", "category", "string", "시장 범주 (kr_stock, kr_etf, us_stock, us_etf)"],
        ["/api/stocks/{symbol}/chart", "symbol", "string", "종목 코드 또는 티커"],
        ["/api/stocks/{symbol}/chart", "category", "string", "시장 범주 (kr_stock, kr_etf, us_stock, us_etf)"],
        ["/api/stocks/{symbol}/chart", "period", "string", "차트 기간 (1m, 3m, 6m, 1y, 기본값: 1m)"],
    ]
)

add_h2(doc, "API 호출 코드 예시")
add_code_block(doc, 
"import requests\n"
"\n"
"# 1. 자동완성 API 호출 예시\n"
"autocomplete_url = 'http://localhost:8000/api/search/autocomplete'\n"
"params = {\n"
"    'q': '삼성',\n"
"    'category': 'kr_stock'\n"
"}\n"
"response = requests.get(autocomplete_url, params=params)\n"
"print(response.json())\n"
"\n"
"# 2. 상세 시세 API 호출 예시\n"
"detail_url = 'http://localhost:8000/api/stocks/005930/detail'\n"
"params = {\n"
"    'category': 'kr_stock'\n"
"}\n"
"response = requests.get(detail_url, params=params)\n"
"print(response.json())"
)

# ── 3. 관련 파일 ──────────────────────────────────────────────────────────────
add_h1(doc, "3. 관련 파일")
add_table(doc,
    headers=["파일 경로", "역할"],
    rows=[
        ["src/backend/app/models/market.py", "AssetCategory, ChartPeriod Literal 타입 정의 및 검색 자동완성, 상세 정보, 차트 데이터용 Pydantic 모델 작성"],
        ["src/backend/app/config.py", "종목 마스터 캐시 TTL (24시간), 상세 시세 캐시 TTL (60초), 프로바이더 타임아웃 환경 설정 추가"],
        ["src/backend/app/providers/krx_provider.py", "KRX Data Marketplace OTP 발급 및 CSV 수집, EUC-KR 디코딩 및 LOGOUT 처리 구현"],
        ["src/backend/app/providers/nasdaq_provider.py", "NASDAQ Trader Symbol Directory 파일 다운로드 및 파이프라인 파싱을 통해 미국 주식/ETF 수집"],
        ["src/backend/app/providers/yahoo_finance.py", "Yahoo Finance chart API 연동, 시세 메타데이터 및 차트 데이터 정규화 파싱 구현"],
        ["src/backend/app/services/search_service.py", "종목 마스터 캐시/Lazy loading, Prefix 우선 랭킹 매칭, 상세/차트 캐싱 및 Stale Fallback 구현"],
        ["src/backend/app/api/routes.py", "/api/search/autocomplete, /api/stocks/{symbol}/detail, /api/stocks/{symbol}/chart 엔드포인트 연동"],
        ["src/backend/app/main.py", "FastAPI lifespan 연동을 통해 백그라운드에서 preload_all_masters() 사전 적재 기동 및 관리"],
        ["src/frontend/src/types/market.ts", "백엔드 응답 명세에 맞춘 TypeScript 인터페이스 선언 및 타입 적용"],
        ["src/frontend/src/api/markets.ts", "fetchAutocomplete, fetchStockDetail, fetchStockChart API 호출 클라이언트 함수 작성"],
        ["src/frontend/src/hooks/useStockSearch.ts", "300ms 디바운스, AbortController 및 ignore 플래그를 통한 비동기 레이스 컨디션 차단"],
        ["src/frontend/src/hooks/useStockDetail.ts", "Promise.allSettled를 통해 상세와 차트 병렬 fetch 및 부분 실패 격리 관리"],
        ["src/frontend/src/components/DashboardTab.tsx", "기존 App.tsx 내부의 대시보드 화면 요소를 그대로 격리 이관하여 안정성 보존"],
        ["src/frontend/src/components/AutocompleteInput.tsx", "방향키, 엔터, ESC 키 조작 및 WAI-ARIA 접근성 속성을 준수한 자동완성 드롭다운"],
        ["src/frontend/src/components/StockDetailPanel.tsx", "종목 정보 그리드 표시 및 KRW 통화일 경우 소수점 제거 포맷팅 적용"],
        ["src/frontend/src/components/StockChart.tsx", "캔들스틱 및 거래량 통합 SVG 직접 렌더링 차트 (0 나누기 방어, 한국/미국 색상 분기, Y축 72px 여백 적용)"],
        ["src/frontend/src/components/SearchTab.tsx", "네 가지 시장 범주 제어 단추, AutocompleteInput, 상세 및 차트 컴포넌트 조합 배치"],
        ["src/frontend/src/App.tsx", "메인 화면에 두 개의 탭을 두고 activeTab 상태에 따라 대시보드 및 종목검색 분기 렌더링"],
        ["src/frontend/src/App.css", "신규 탭 네비게이션, 자동완성 팝오버, SVG 차트 및 반응형 스타일 시트 추가"],
        ["tests/backend/test_krx_provider.py", "KRX 다운로드, EUC-KR 디코딩, LOGOUT 감지 예외 격리 단위 테스트"],
        ["tests/backend/test_nasdaq_provider.py", "NASDAQ 데이터 파싱 및 ETF/주식 분리, 다운로드 실패 격리 단위 테스트"],
        ["tests/backend/test_yahoo_finance_provider.py", "Yahoo Finance chart API 파싱 및 Null-safe 엣지 케이스 단위 테스트"],
        ["tests/backend/test_search_service.py", "검색어 랭킹 정렬, 캐싱, unavailable 응답 시 Stale Fallback 동작 단위 테스트"],
        ["tests/backend/test_search_routes.py", "자동완성 입력 검증 및 잘못된 카테고리 422 에러, camelCase 직렬화 API 검증 테스트"],
        ["tests/frontend/SearchTab.test.tsx", "프론트엔드 탭 전환, 디바운스, 0 나누기 방어 차트, 부분 실패 격리, KRW 포맷팅 통합 테스트"],
    ]
)

# ── 4. 주요 설계 결정 ─────────────────────────────────────────────────────────
add_h1(doc, "4. 주요 설계 결정")
add_h2(doc, "구현 접근 방식 및 근거")
add_paragraph(doc, "백엔드에서는 기존 MarketService와 비즈니스 역할을 완전히 격리하기 위해 SearchService 및 신규 전용 프로바이더들을 구현하였다. 백그라운드 태스크로 종목 마스터 데이터를 사전에 수집하되(lifespan), 외부 사이트 다운이나 장애 등으로 앱 전체 기동이 멈추는 것을 방지하고자 try-except로 수집 실패 예외를 격리하고, 첫 검색 요청이 들어올 때 Lock 하에 Lazy Loading으로 재시도하도록 2중 복구 구조를 구성하였다.")
add_paragraph(doc, "또한 외부 시세 provider 호출 실패 시 기존 캐시가 있다면 Stale 상태로 응답을 내려주도록 설계하여 외부 연동 장애 시 부분 작동을 보장했다.")
add_paragraph(doc, "프론트엔드에서는 런타임 추가 의존성이나 TypeScript 컴파일 및 빌드 리스크가 있는 외부 차트 라이브러리(Recharts 등) 대신, 순수 SVG와 HTML/CSS 좌표 계산을 활용한 캔들스틱 및 거래량 통합 차트를 직접 렌더링하였다.")

add_h2(doc, "검토한 대안")
add_bullet(doc, "대안 1: 정적 로컬 시드 파일 기반 종목 마스터 - 신규 상장 종목이 반영되지 않아 '최신 종목의 항시 반영'이라는 요구사항에 반하므로 미채택.")
add_bullet(doc, "대안 2: KRX OpenAPI 공식 키 연동 - 비대화식 자동화 테스트 환경(interactive_mode: false)에서 자격 증명을 동적으로 취득하고 검증하는 것이 불가능하여 미채택.")
add_bullet(doc, "대안 3: Recharts 등 외부 차트 패키지 도입 - 새 npm 패키지로 인해 의존성 복잡도가 커지고 컴파일 위험을 유발하여 순수 SVG 좌표 계산 직접 렌더링 방식으로 대체 채택.")

add_h2(doc, "리뷰 핵심 포인트 및 최종 결정")
add_bullet(doc, "stale fallback 동작 무력화 버그 수정: YahooFinanceProvider가 unavailable 상태를 정상 객체로 리턴하면 SearchService의 except 블록에 가지 못하던 문제를 해결하기 위해, SearchService에서 직접 unavailable 상태를 감지하여 캐시된 stale 데이터를 반환하도록 수정 완료.")
add_bullet(doc, "프론트엔드 API 부분 실패 격리: Promise.all을 Promise.allSettled로 전면 수정하여 차트 API 호출이 실패하더라도 상세 시세 패널은 정상 렌더링을 유지하고 차트 영역에만 에러/빈 화면 오버레이를 표출하도록 부분 실패 격리 완료.")
add_bullet(doc, "KRW 통화 가격 소수점 제거: 원화 금액(예: 70,000.00원)에 불필요한 소수점이 붙지 않도록 formatPrice 함수 내에 통화 분기 분기를 추가하여 가독성 개선 완료.")
add_bullet(doc, "한국 주식/ETF 차트 색상 관례 적용: 상승 시 빨간색, 하락 시 파란색으로 표현되도록 category prop을 연동해 한국 종목과 미국 종목(상승 녹색, 하락 빨간색) 간 캔들 및 거래량 바 색상을 분기 처리 완료.")
add_bullet(doc, "SVG 가격 잘림 방지: Y축 눈금 라벨이 위치한 공간 PAD_LEFT를 56에서 72로 증가하여 고가 종목의 가격 라벨이 SVG 경계 바깥으로 잘려 보이는 문제 예방 완료.")

add_h2(doc, "거부한 지적 사항 및 사유")
add_bullet(doc, "SearchService 내 _load_lock 카테고리별 분산 관리: 현재 preload_all_masters()는 순차적으로 4개 카테고리를 백그라운드 태스크로 로딩하므로 lock 분리의 실질적인 성능 이득이 극히 미미하다. 오히려 코드의 복잡도를 가중시키므로 거부 처리함.")

# ── 5. 의존성 ─────────────────────────────────────────────────────────────────
add_h1(doc, "5. 의존성")
add_table(doc,
    headers=["라이브러리 / 모듈", "용도"],
    rows=[
        ["python-docx", "기능 명세서 문서 파일(.docx) 자동 생성 및 포맷팅 지원 (프로덕션 미포함)"],
        ["httpx", "KRX Data Marketplace, Nasdaq Trader, Yahoo Finance 외부 API 비동기 HTTP 통신"],
        ["pydantic", "백엔드 API 요청/응답 스키마 선언 및 자동 검증 (v2 버전 사용)"],
        ["lucide-react", "프론트엔드 탭 전환, 검색 아이콘 및 경고 뱃지 렌더링용 아이콘 라이브러리"],
    ]
)

# ── 6. 테스트 현황 ────────────────────────────────────────────────────────────
add_h1(doc, "6. 테스트 현황")
add_table(doc,
    headers=["테스트 파일 경로", "커버하는 범위 요약", "최종 결과"],
    rows=[
        ["tests/backend/test_krx_provider.py", "KRX OTP 발급, CSV 데이터 파싱, LOGOUT 감지 예외 격리, EUC-KR 디코딩 검증", "PASS"],
        ["tests/backend/test_nasdaq_provider.py", "NASDAQ 기동 파일 다운로드 실패 시 격리, Test Issue 및 메타 행 필터링, ETF/주식 분리 검증", "PASS"],
        ["tests/backend/test_yahoo_finance_provider.py", "Yahoo Finance chart API 연동, 시세 파싱, Null-safe 처리 및 오류 시 unavailable 반환 검증", "PASS"],
        ["tests/backend/test_search_service.py", "Prefix/Substring 랭킹 매칭, 10개 제한 캐싱, unavailable 상태 응답 시 Stale Fallback 반환 작동 검증", "PASS"],
        ["tests/backend/test_search_routes.py", "API 엔드포인트 응답 형식 검증, 2자 미만 400 에러 및 유효하지 않은 카테고리 422 에러, camelCase 직렬화 검증", "PASS"],
        ["tests/frontend/SearchTab.test.tsx", "프론트엔드 탭 내비게이션 동작, 디바운스 타이핑, 0으로 나누기 방어 SVG 차트, 부분 실패 격리, KRW 포맷팅 검증", "PASS"],
    ]
)

add_h2(doc, "테스트 실행 명령 및 종합 통과 상태")
add_bullet(doc, "백엔드 테스트 실행: python -m pytest tests/backend/ -v (48개 테스트 전부 PASS)")
add_bullet(doc, "프론트엔드 테스트 실행: npm test (21개 테스트 전부 PASS)")
add_bullet(doc, "프론트엔드 빌드 검증: npm run build (컴파일 에러 없이 성공)")

# ── 7. 알려진 한계 및 추후 개선 ──────────────────────────────────────────────
add_h1(doc, "7. 알려진 한계 및 추후 개선")
add_bullet(doc, "휴장일 마스터 데이터 갱신 제한: KRX는 당일 거래일 기준으로 종목 마스터 정보를 제공하므로 주말/공휴일에는 호출 실패 가능성이 있다. 이를 위해 lazy loading 재시도 및 메모리 stale 캐시를 활용해 복구하도록 처리함.")
add_bullet(doc, "외부 API 구조 변동 가능성: 야후 파이낸스 차트 API는 비공식 무료 엔드포인트이므로 구조 변동 시 파싱 오류의 위험이 존재한다. 대응을 위해 파서 내부를 try-except로 완전히 묶어 unavailable 응답으로 격리시킴으로써 백엔드 충격을 원천 차단함.")
add_bullet(doc, "차트 기능 확장: 순수 SVG 직접 계산으로 캔들 차트를 렌더링했으나 툴팁 표시나 드래그 줌 같은 상호작용 기능이 누락됨. 향후 의존성 리스크가 검증된 시점에 Recharts 등의 도입을 검토 가능.")

# ── 저장 ──────────────────────────────────────────────────────────────────────
os.makedirs(".ai/docs", exist_ok=True)
doc.save(".ai/docs/02-project-search-tab_명세서.docx")
print("생성 완료: .ai/docs/02-project-search-tab_명세서.docx")
