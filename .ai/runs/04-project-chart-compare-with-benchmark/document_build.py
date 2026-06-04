import sys, os
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
        ["기능 이름", "차트 가독성 개선 및 한국 주식 검색/이벤트 오류 디버깅"],
        ["기능 목적", "차트에 그리드와 거래량 기준선을 추가하고, 한국 주식 검색 오류 및 기간 변경 시 차트 이벤트 단절 버그를 해결합니다."],
        ["최종 판정", "PASS"],
        ["최종 완성 일시", "2026-06-05"],
    ]
)

# ── 2. 사용 방법 ──────────────────────────────────────────────────────────────
add_h1(doc, "2. 사용 방법")
add_h2(doc, "인터페이스 설명 및 자동완성 API")
add_bullet(doc, "자동완성 API 엔드포인트: GET /api/search/autocomplete")
add_bullet(doc, "쿼리 파라미터: q (검색어, 한글명 또는 6자리 종목코드), category (kr_stock, kr_etf 등)")
add_bullet(doc, "차트 컴포넌트: StockChart (props로 bars 데이터, period, isLoading 등을 전달받아 렌더링)")

add_h2(doc, "차트 데이터 구조 (ChartResponse)")
add_code_block(doc, 
"{\n"
"  \"bars\": [\n"
"    {\n"
"      \"timestamp\": 1672531200,\n"
"      \"open\": 72000.0,\n"
"      \"high\": 73500.0,\n"
"      \"low\": 71800.0,\n"
"      \"close\": 73000.0,\n"
"      \"volume\": 15000000\n"
"    }\n"
"  ],\n"
"  \"symbol\": \"005930\",\n"
"  \"status\": \"success\"\n"
"}"
)

# ── 3. 관련 파일 ──────────────────────────────────────────────────────────────
add_h1(doc, "3. 관련 파일")
add_table(doc,
    headers=["파일 경로", "역할"],
    rows=[
        ["src/frontend/src/components/StockChart.tsx", "Callback Ref 기반 wheel 리스너 바인딩 및 세로/가로 그리드, 거래량 기준선 렌더링"],
        ["src/frontend/src/services/chartHelpers.ts", "차트 렌더링용 x축 날짜 라벨 샘플링 인덱스 계산(sampleIndices) 함수 정의"],
        ["src/backend/app/providers/krx_provider.py", "KRX CSV 마스터 파싱 시 BOM 및 공백 제거, HTML/LOGOUT 에러 응답 방어 처리"],
        ["src/backend/app/services/search_service.py", "한국 카테고리 종목명 및 종목코드 매칭, 중복 반환 방지, 마스터 로딩 실패 로그 처리"],
        ["tests/frontend/StockChart.test.tsx", "그리드 렌더링 및 로딩 마운트 해제 후 wheel 리스너 복구 상태 검증 테스트"],
        ["tests/frontend/SearchTab.test.tsx", "한국 주식 탭에서 종목명/종목코드 검색 시 자동완성 렌더링 검증 테스트"],
        ["tests/backend/test_krx_provider.py", "BOM 및 공백이 포함된 CSV 파싱 및 에러 페이지 방어 기능 검증 테스트"],
        ["tests/backend/test_search_service.py", "종목코드 검색 매칭, 부분 prefix 매치, 중복 결과 제거 검증 테스트"]
    ]
)

# ── 4. 주요 설계 결정 ─────────────────────────────────────────────────────────
add_h1(doc, "4. 주요 설계 결정")
add_h2(doc, "구현 접근 방식")
add_paragraph(doc, "React의 선언적 렌더링에서 SVG가 로딩 상태에 따라 마운트/언마운트될 때, 기존 'useEffect' 최초 1회 바인딩으로 인해 리스너가 누락되는 현상이 발생했습니다. 이를 해결하고자 Callback Ref와 'svgNode' 상태를 이용해 SVG 엘리먼트의 생성 및 제거 수명주기에 직접 wheel 리스너의 등록과 해제를 동기화했습니다. 또한 KRX CSV 파싱 시 BOM(byte order mark) 및 공백 문자로 인해 컬럼 딕셔너리 매칭이 완전히 무산되는 현상을 방어하기 위해, CSV 텍스트 선두의 BOM을 제거하고 행 데이터의 모든 키와 값을 양방향으로 정규화하는 이중 전처리 파이프라인을 구축했습니다.")

add_h2(doc, "검토한 대안")
add_bullet(doc, "대안 A: useEffect 의존성 배열에 period/data 등을 주입하여 리스너 재바인딩 — 채택하지 않은 이유: SVG의 리마운트를 유발하는 모든 비동기 상태 변화를 일일이 추적해야 하므로 누락 위험 및 코드 복잡도가 높아 기각했습니다.")
add_bullet(doc, "대안 B: D3.js 등의 외부 차트 라이브러리 도입 — 채택하지 않은 이유: 기존에 구현된 SVG 기반 StockChart 소스코드를 안정적으로 유지 및 가산적으로 확장한다는 요구 범위에 어긋나고 불필요한 의존성 위험을 방지하기 위해 기각했습니다.")

add_h2(doc, "리뷰 핵심 포인트")
add_bullet(doc, "Callback Ref를 통해 SVG 노드가 갱신될 때에만 이벤트가 정상 재연결되는지에 대한 구조적 검증이 이루어졌으며, 예기치 않은 메모리 누수 방지를 위해 cleanup 함수를 완벽히 매칭하는 설계가 승인되었습니다.")
add_bullet(doc, "KRX CSV 디코딩 시 유입될 수 있는 비정상 HTML/LOGOUT 페이지에 대해 예외가 발생하더라도 빈 결과를 리턴하도록 격리 조치한 견고함이 평가되었습니다.")

add_h2(doc, "거부/보류 항목")
add_bullet(doc, "보류 항목: StockChart 내부에 하드코딩된 그리드 및 보조선 색상(Hex 값)의 CSS 변수 토큰화 — 사유: 테마/다크 모드는 현재 기능 요구 범위 밖의 사안이며, 기존 테스트 파일에서 Hex 값을 엄격히 비교하는 단언문이 존재하여 변경 시 사이드 이펙트 우려로 보류했습니다.")

# ── 5. 의존성 ─────────────────────────────────────────────────────────────────
add_h1(doc, "5. 의존성")
add_table(doc,
    headers=["라이브러리/프레임워크", "용도"],
    rows=[
        ["React 18", "프론트엔드 UI 컴포넌트 렌더링 및 상태 관리"],
        ["FastAPI", "백엔드 API 엔드포인트 구축"],
        ["Pydantic", "백엔드 데이터 모델링 및 스키마 검증"],
        ["pytest", "백엔드 비즈니스 로직 및 파서 단위 테스트"],
        ["vitest", "프론트엔드 컴포넌트 및 렌더링 단위 테스트"]
    ]
)

# ── 6. 테스트 현황 ────────────────────────────────────────────────────────────
add_h1(doc, "6. 테스트 현황")
add_table(doc,
    headers=["테스트 파일", "커버 범위", "결과"],
    rows=[
        ["tests/frontend/StockChart.test.tsx", "그리드 컴포넌트 렌더링, sampleIndices 엣지 케이스, SVG 재마운트 시 wheel 이벤트 복구 검증", "PASS"],
        ["tests/frontend/SearchTab.test.tsx", "한국 주식 탭에서 한글명/종목코드 자동완성 API 호출 및 dropdown 리스트 바인딩 검증", "PASS"],
        ["tests/backend/test_krx_provider.py", "KRX CSV 헤더에 BOM/공백 존재 시 정상 파싱 복구 및 비정상 HTML/LOGOUT 응답 시 방어 검증", "PASS"],
        ["tests/backend/test_search_service.py", "종목코드 검색 매칭, 부분 prefix 매치, 중복 결과 제거 및 마스터 로딩 실패 로그 검증", "PASS"]
    ]
)

# ── 7. 알려진 한계 및 추후 개선 ──────────────────────────────────────────────
add_h1(doc, "7. 알려진 한계 및 추후 개선")
add_bullet(doc, "현재 그리드 보조선 색상 값들이 인라인 Hex 코드로 하드코딩되어 있습니다. 추후 다크 모드 등 글로벌 테마를 도입하는 경우, App.css 내 디자인 토큰으로 통합 추출하는 리팩터링이 수반되어야 합니다.")
add_bullet(doc, "한국 주식/ETF 검색 시 현재는 단순한 prefix 및 substring 매칭을 제공하므로, 초성 검색이나 키워드 오타 교정 같은 복잡한 검색 경험을 제공하지 못합니다. 향후 형태소 분석이나 전문 검색 엔진 도입 검토가 필요합니다.")

# ── 저장 ──────────────────────────────────────────────────────────────────────
os.makedirs(".ai/docs", exist_ok=True)
doc.save(".ai/docs/04-project-chart-compare-with-benchmark_명세서.docx")
print("생성 완료: .ai/docs/04-project-chart-compare-with-benchmark_명세서.docx")
