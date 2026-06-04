# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, ".ai/templates")

from docx_helper import (  # noqa: E402
    add_bullet,
    add_code_block,
    add_h1,
    add_h2,
    add_paragraph,
    add_table,
    create_doc,
)


OUTPUT_PATH = ".ai/docs/01-project-init_명세서.docx"


def build_document() -> None:
    doc = create_doc()
    doc.core_properties.title = "주식 대시보드 프로젝트 초기화 명세서"
    doc.core_properties.subject = "React와 FastAPI 기반 무료 시장 데이터 대시보드"

    add_h1(doc, "1. 개요")
    add_table(
        doc,
        headers=["항목", "내용"],
        rows=[
            ["기능 이름", "주식 대시보드 프로젝트 초기화"],
            [
                "기능 목적",
                "미국, 한국, 기타 주요국 대표지수와 주요 환율을 한 화면에서 조회하는 React/FastAPI 대시보드 초기 구조를 제공한다.",
            ],
            ["최종 판정", "PASS"],
            ["최종 완성 일시", "2026-06-04"],
            [
                "문서 스타일 결정",
                "개발자용 기능 명세서 성격에 맞춰 compact reference guide 형태로 작성하고, 필수 helper 템플릿의 기본 서식을 적용했다.",
            ],
        ],
    )
    add_paragraph(
        doc,
        "이 명세서는 검증을 통과한 구현 결과만 요약한다. 무료 데이터 공급자의 지연이나 심볼 지원 변경 가능성은 한계 항목에 별도로 기록했다.",
    )

    add_h1(doc, "2. 사용 방법")
    add_h2(doc, "실행 스크립트")
    add_paragraph(
        doc,
        "Windows 환경에서 src 디렉터리의 배치파일을 사용해 백엔드와 프론트엔드를 함께 실행하거나 종료한다. 기본 포트는 백엔드 8000, 프론트엔드 5173이며 환경변수로 변경할 수 있다.",
    )
    add_code_block(
        doc,
        "cd src\nstart-dashboard.bat\n\nrem 다른 콘솔에서 종료할 때\nstop-dashboard.bat",
    )
    add_h2(doc, "API 엔드포인트")
    add_table(
        doc,
        headers=["엔드포인트", "파라미터", "반환", "비고"],
        rows=[
            [
                "GET /api/health",
                "없음",
                "status, cacheTtlSeconds, providers",
                "서버 상태와 공급자 설정 상태 확인",
            ],
            [
                "GET /api/markets/summary",
                "없음",
                "generatedAt, cacheTtlSeconds, status, indices, exchangeRates",
                "프론트엔드가 기본 호출하는 통합 대시보드 데이터",
            ],
            [
                "GET /api/markets/indices",
                "없음",
                "generatedAt, cacheTtlSeconds, status, items",
                "대표지수 목록만 반환",
            ],
            [
                "GET /api/markets/exchange-rates",
                "없음",
                "generatedAt, cacheTtlSeconds, status, items",
                "환율 목록만 반환",
            ],
        ],
    )
    add_h2(doc, "응답 필드")
    add_bullet(
        doc,
        "각 시장 항목은 id, name, category, region, symbol, value, change, changePercent, currency, asOf, source, status, errorMessage를 포함한다.",
    )
    add_bullet(doc, "항목 상태는 ok, stale, unavailable 중 하나이며, 통합 상태는 ok, partial, unavailable 중 하나다.")
    add_bullet(doc, "무료 공급자의 실패나 무효값은 전체 응답 실패 대신 개별 항목의 unavailable 또는 stale 상태로 표현한다.")
    add_h2(doc, "호출 예시")
    add_code_block(
        doc,
        "Invoke-RestMethod http://127.0.0.1:8000/api/markets/summary | ConvertTo-Json -Depth 5",
    )
    add_h2(doc, "출력 예시")
    add_code_block(
        doc,
        '{\n'
        '  "generatedAt": "2026-06-04T12:00:00Z",\n'
        '  "cacheTtlSeconds": 30,\n'
        '  "status": "partial",\n'
        '  "indices": [\n'
        '    {\n'
        '      "id": "sp500",\n'
        '      "name": "S&P 500",\n'
        '      "value": 5300.12,\n'
        '      "changePercent": 0.42,\n'
        '      "asOf": "2026-06-04T11:59:00Z",\n'
        '      "source": "Stooq CSV",\n'
        '      "status": "ok"\n'
        '    }\n'
        '  ],\n'
        '  "exchangeRates": []\n'
        '}',
    )

    add_h1(doc, "3. 관련 파일")
    add_table(
        doc,
        headers=["파일 경로", "역할"],
        rows=[
            ["src/start-dashboard.bat", "Windows에서 백엔드와 프론트엔드를 함께 실행하고 PID와 로그를 기록한다."],
            ["src/stop-dashboard.bat", "PID 파일과 제한된 포트 매칭을 사용해 대시보드 프로세스를 종료한다."],
            ["src/backend/requirements.txt", "FastAPI 백엔드와 테스트 실행에 필요한 Python 의존성을 정의한다."],
            ["src/backend/app/main.py", "FastAPI 앱 생성, CORS 설정, 라우터 등록을 담당한다."],
            ["src/backend/app/config.py", "BACKEND_PORT, CACHE_TTL_SECONDS, CORS_ORIGINS 설정을 로드한다."],
            ["src/backend/app/api/routes.py", "health, summary, indices, exchange-rates API 라우트를 제공한다."],
            ["src/backend/app/models/market.py", "시장 항목과 응답 컬렉션의 Pydantic 스키마를 정의한다."],
            ["src/backend/app/providers/symbols.py", "기본 지수와 환율 심볼 목록을 관리한다."],
            ["src/backend/app/providers/stooq.py", "Stooq CSV quote 응답을 정규화한다."],
            ["src/backend/app/providers/frankfurter.py", "Frankfurter 환율 fallback 응답을 정규화한다."],
            ["src/backend/app/services/cache.py", "TTL 기반 인메모리 캐시를 제공한다."],
            ["src/backend/app/services/market_service.py", "공급자 호출, fallback, 캐시, 상태 정규화를 통합하는 서비스 레이어다."],
            ["src/frontend/package.json", "React, Vite, Vitest 실행 스크립트와 의존성을 정의한다."],
            ["src/frontend/src/api/markets.ts", "프론트엔드의 summary API fetch 함수를 제공한다."],
            ["src/frontend/src/hooks/useMarketSummary.ts", "초기 로딩, 수동 새로고침, 자동 갱신, 오류 상태를 관리한다."],
            ["src/frontend/src/App.tsx", "대시보드 화면의 최상위 렌더링을 담당한다."],
            ["src/frontend/src/components/DashboardHeader.tsx", "새로고침 버튼, 자동 갱신 토글, 기준 시각 정보를 표시한다."],
            ["src/frontend/src/components/MarketSection.tsx", "시장 카테고리별 섹션을 렌더링한다."],
            ["src/frontend/src/components/MarketTable.tsx", "시장 데이터 테이블을 렌더링한다."],
            ["src/frontend/src/components/StatusBadge.tsx", "ok, stale, unavailable 상태 배지를 표시한다."],
        ],
    )

    add_h1(doc, "4. 주요 설계 결정")
    add_h2(doc, "구현 접근 방식")
    add_paragraph(
        doc,
        "백엔드는 라우터, 서비스 레이어, 캐시, 데이터 공급자 어댑터, 모델을 분리했다. 이 구조는 무료 API 실패 처리를 서비스 계층에 집중시키고, 향후 공급자를 교체하거나 보강할 때 변경 범위를 줄인다.",
    )
    add_paragraph(
        doc,
        "프론트엔드는 React, Vite, TypeScript를 사용하고 React 내장 상태와 커스텀 훅으로 로딩, 갱신, 오류 상태를 관리한다. 대시보드는 대표지수와 환율을 구역별 표로 보여주며 각 항목에 기준 시각, 출처, 상태를 노출한다.",
    )
    add_h2(doc, "채택한 데이터 전략")
    add_bullet(doc, "Stooq CSV를 지수와 환율의 우선 무료 공급자로 사용한다.")
    add_bullet(doc, "Stooq 환율 데이터가 없을 때 Frankfurter 최신 환율 API를 fallback으로 사용하고 stale 상태로 표시한다.")
    add_bullet(doc, "동일 요청의 외부 호출을 줄이기 위해 30초 TTL 인메모리 캐시를 사용한다.")
    add_bullet(doc, "외부 공급자 예외는 개별 공급자 단위로 격리하고 빈 결과로 대체해 다른 데이터 처리를 계속한다.")
    add_h2(doc, "검토했지만 채택하지 않은 대안")
    add_bullet(doc, "단일 모놀리식 백엔드 파일 구조: 외부 API 실패, 캐시, 라우팅 책임이 섞여 유지보수가 어려워 제외했다.")
    add_bullet(doc, "Stooq 단독 사용: 환율 누락 시 대체 경로가 없어 Frankfurter fallback을 병행하기로 했다.")
    add_h2(doc, "위험 구간과 완화 방안")
    add_bullet(doc, "포트 충돌과 잘못된 프로세스 종료 위험은 시작 전 netstat 검사, PID 파일 기록, 제한된 명령줄 매칭으로 완화했다.")
    add_bullet(doc, "무료 API 장애와 rate limit 위험은 TTL 캐시, stale 캐시 반환, 공급자별 예외 격리로 완화했다.")
    add_bullet(doc, "Python, Node, npm 미설치 위험은 시작 스크립트의 사전 명령 검사로 사용자에게 명확한 실패 메시지를 반환하도록 했다.")
    add_h2(doc, "리뷰 반영 결과")
    add_bullet(doc, "MAJOR 지적이었던 공급자 통신 장애의 연쇄 실패 가능성은 공급자별 try-except 격리로 수정했다.")
    add_bullet(doc, "공급자 HTTP timeout 기본값은 8초에서 4초로 낮춰 응답성을 개선했다.")
    add_bullet(doc, "데이터가 없는 항목의 source는 오해를 줄이기 위해 N/A로 표시하도록 변경했다.")
    add_bullet(doc, "start-dashboard.bat의 차단 오류 시 pause 추가 제안은 무인 자동 실행을 멈출 수 있어 거부했다.")
    add_bullet(doc, "KOSDAQ 또는 KOSPI 200 추가 표시는 Stooq 무료 quote 응답에서 유효하지 않은 값이 확인되어 현재 구현에서는 KOSPI만 채택했다.")

    add_h1(doc, "5. 의존성")
    add_table(
        doc,
        headers=["영역", "라이브러리", "용도"],
        rows=[
            ["백엔드", "fastapi", "API 서버와 라우터 구현"],
            ["백엔드", "uvicorn", "ASGI 개발 서버 실행"],
            ["백엔드", "httpx", "Stooq와 Frankfurter에 대한 비동기 HTTP 호출"],
            ["백엔드", "pydantic", "응답 모델과 camelCase 별칭 직렬화"],
            ["백엔드 테스트", "pytest", "백엔드와 배치파일 스모크 테스트 실행"],
            ["백엔드 테스트", "pytest-asyncio", "비동기 공급자와 서비스 테스트 실행"],
            ["프론트엔드", "react, react-dom", "대시보드 UI 렌더링"],
            ["프론트엔드", "lucide-react", "UI 아이콘 표시"],
            ["프론트엔드 빌드", "vite, typescript, @vitejs/plugin-react", "개발 서버, TypeScript 빌드, React 플러그인"],
            ["프론트엔드 테스트", "vitest, jsdom, @testing-library/react", "컴포넌트와 훅 단위 테스트"],
            ["프론트엔드 타입", "@types/react, @types/react-dom", "TypeScript 타입 지원"],
        ],
    )

    add_h1(doc, "6. 테스트 현황")
    add_table(
        doc,
        headers=["테스트 파일", "커버 범위", "최종 결과"],
        rows=[
            ["tests/backend/test_stooq_provider.py", "Stooq CSV 파싱, 무효값 처리, 변동값 계산, timeout 기본값", "PASS"],
            ["tests/backend/test_frankfurter_provider.py", "Frankfurter 환율 정규화, 실패 처리, timeout 기본값", "PASS"],
            ["tests/backend/test_market_service.py", "서비스 캐시, 부분 실패, stale fallback, 공급자 예외 격리, N/A source", "PASS"],
            ["tests/backend/test_routes.py", "FastAPI health, summary, indices, exchange-rates 라우트 응답", "PASS"],
            ["tests/frontend/App.test.tsx", "대시보드 로딩, 구역 렌더링, 부분 실패 표시", "PASS"],
            ["tests/frontend/useMarketSummary.test.tsx", "수동 새로고침, 자동 갱신 토글, 타이머 동작", "PASS"],
            ["tests/scripts/test_batch_files.py", "start/stop 배치파일 존재, 포트/PID/종료 명령 구조", "PASS"],
        ],
    )
    add_h2(doc, "최종 검증 명령")
    add_code_block(
        doc,
        "python -m pytest tests/backend tests/scripts -p no:cacheprovider\n"
        "npm.cmd test\n"
        "npm.cmd run build",
    )
    add_paragraph(
        doc,
        "최종 검증 결과는 backend/scripts 15개 통과, frontend 6개 통과, frontend build 성공으로 기록되었다. 추가 테스트 작성은 없었으며, 수정 단계에서 추가된 공급자 예외 격리 테스트가 정상 통과했다.",
    )

    add_h1(doc, "7. 알려진 한계 및 추후 개선")
    add_bullet(doc, "Stooq와 Frankfurter는 무료 API이므로 거래소별 지연, 휴장일, 심볼 지원 변경, 일시적 장애가 발생할 수 있다.")
    add_bullet(doc, "Frankfurter fallback 환율은 일간 기준 값이므로 전일 대비 변동값을 제공하지 않고 stale 상태로 표시한다.")
    add_bullet(doc, "현재 캐시는 프로세스 메모리 기반이라 서버 재시작 시 초기화된다.")
    add_bullet(doc, "KOSDAQ 또는 KOSPI 200은 무료 quote 응답이 유효해지면 심볼 목록과 테스트를 보강해 추가할 수 있다.")
    add_bullet(doc, "관심종목, 포트폴리오, 주문, 사용자 인증, 유료 API, DB 저장, Docker와 클라우드 배포는 이번 범위에서 제외되었다.")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    doc.save(OUTPUT_PATH)
    print(f"생성 완료: {OUTPUT_PATH}")


if __name__ == "__main__":
    build_document()
