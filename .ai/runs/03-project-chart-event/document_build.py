import sys
import os

# templates 경로 추가
sys.path.insert(0, ".ai/templates")
from docx_helper import (
    create_doc, add_h1, add_h2, add_paragraph,
    add_bullet, add_code_block, add_table
)

def build_docx():
    doc = create_doc()

    # ── 1. 개요 ──────────────────────────────────────────────────────────────────
    add_h1(doc, "1. 개요")
    add_table(doc,
        headers=["구분", "상세 내용"],
        rows=[
            ["기능 명칭", "종목 차트 기간 확장 및 휠 줌/드래그 이동/미니맵 기능 구현"],
            ["기능 목적", "다양한 조회 기간(1M~10Y, YTD) 지원 및 마우스/트랙패드 상호작용과 미니맵 제공을 통한 차트 탐색 UX 개선"],
            ["최종 판정", "PASS (검증 단계 최종 통과)"],
            ["최종 완성 일시", "2026-06-04"],
        ]
    )
    add_paragraph(doc, "본 기능은 긴 조회 기간의 주식 차트를 사용자가 원활하게 탐색할 수 있도록 돕습니다. 마우스 휠 및 드래그 제스처로 뷰포트를 편리하게 조작하고, 미니맵을 통해 전체 데이터 대비 현재 위치를 직관적으로 파악할 수 있는 고급 차트 시스템입니다.")

    # ── 2. 사용 방법 ──────────────────────────────────────────────────────────────
    add_h1(doc, "2. 사용 방법")
    add_h2(doc, "백엔드 API 규격")
    add_bullet(doc, "엔드포인트: GET /api/stocks/{symbol}/chart")
    add_bullet(doc, "조회 기간 파라미터: period (조회 범위 지정)")
    add_bullet(doc, "허용값 목록: 1m, 3m, 6m, 1y, 3y, 5y, 10y, ytd (기본값: 1m)")
    
    add_h2(doc, "프론트엔드 React 컴포넌트 호출 예시")
    add_paragraph(doc, "차트 컴포넌트는 단일 종목의 가격 및 거래량 차트를 렌더링하며, 사용자의 조작 이벤트를 부모 컴포넌트로 전달합니다.")
    
    react_code = (
        "import React, { useState } from 'react';\n"
        "import StockChart from './components/StockChart';\n"
        "import { ChartPeriod, ChartResponse } from '../types/market';\n\n"
        "function StockDetail({ symbol, chartData }: { symbol: string; chartData: ChartResponse }) {\n"
        "    const [period, setPeriod] = useState<ChartPeriod>('1m');\n\n"
        "    return (\n"
        "        <StockChart\n"
        "            symbol={symbol}\n"
        "            category='us_stock'\n"
        "            data={chartData}\n"
        "            period={period}\n"
        "            onPeriodChange={(newPeriod) => setPeriod(newPeriod)}\n"
        "        />\n"
        "    );\n"
        "}"
    )
    add_code_block(doc, react_code)

    # ── 3. 관련 파일 ──────────────────────────────────────────────────────────────
    add_h1(doc, "3. 관련 파일")
    add_table(doc,
        headers=["파일 경로", "주요 역할 및 변경 사항"],
        rows=[
            ["src/backend/app/models/market.py", "ChartPeriod 리터럴 정의에 3y, 5y, 10y, ytd 신규 기간 추가"],
            ["src/backend/app/providers/yahoo_finance.py", "Yahoo Finance API 호출 시 대응할 range 및 interval 1d 매핑 파라미터 설정"],
            ["src/frontend/src/types/market.ts", "프론트엔드 ChartPeriod 공용 타입 정의에 3y, 5y, 10y, ytd 추가"],
            ["src/frontend/src/services/chartHelpers.ts", "줌/팬 연산, 오프셋 제한, 날짜 포맷, 미니맵 영역 패스 생성을 담당하는 순수 함수 모듈"],
            ["src/frontend/src/components/StockChart.tsx", "8개 기간 버튼 UI 렌더링, wheel 및 pointer 드래그 감지, 동적 가격축 스케일링, SVG 미니맵 렌더링 구현"],
            ["src/frontend/src/App.css", "차트 기간 선택지 flex 줄바꿈 속성 추가, 휠/드래그 조작 전용 마우스 커서 및 텍스트 드래그 방지 스타일링"]
        ]
    )

    # ── 4. 주요 설계 결정 ─────────────────────────────────────────────────────────
    add_h1(doc, "4. 주요 설계 결정")
    add_h2(doc, "구현 접근 방식 및 선정 배경")
    add_bullet(doc, "기존 SVG 확장: 무거운 차트 라이브러리를 추가하는 대신, 기존에 최적화되어 있던 순수 SVG 코드를 직접 제어하여 번들 크기를 줄이고 통일된 테마 색상(한/미 상승·하락장 색)을 완벽히 재활용했습니다.")
    add_bullet(doc, "슬라이싱 기반 가상 렌더링: 10년 치 일봉 데이터(~2500개)를 한 번에 그리면 브라우저 프레임 저하가 발생하므로, 확대 범위에 맞추어 현재 화면에 보이는 데이터(visibleBars)만 슬라이싱하여 SVG 요소 개수를 효과적으로 제한했습니다.")
    add_bullet(doc, "센티널(null) 패턴 도입: 줌인/줌아웃 상태를 나타내는 view 상태의 기본값을 null로 설정하여 전체 범위를 직관적으로 표시하도록 구현했습니다. 이로써 React 렌더링 타이밍 이슈로 인해 컴포넌트가 마운트될 때 미니맵이 미세하게 흔들리거나 깜빡이는 부작용을 사전에 예방했습니다.")

    add_h2(doc, "검토하였으나 제외된 대안 및 미채택 사유")
    add_bullet(doc, "외부 차트 라이브러리 도입: 줌/팬 기능이 기본 내장되어 있으나, 기존 차트의 디테일한 스타일, 레이아웃 정합성, 한글 깨짐 방지 처리 등 레거시 스타일링과의 마이그레이션 부담이 과도하여 순수 SVG 확장이 훨씬 합리적이라고 판단했습니다.")
    add_bullet(doc, "서버 사이드 줌/팬 렌더링: 확대나 이동 시마다 서버에 새로운 범위의 데이터를 요청하는 대안은 API 복잡도를 가중시키고 네트워크 통신 지연으로 인해 사용자 반응성이 극도로 버벅이는 치명적인 단점이 있어 기각했습니다.")

    add_h2(doc, "품질 검토 과정에서의 추가 수정(Call Stack Overflow 방어)")
    add_bullet(doc, "JS 스프레드 연산자 제거: 기존의 Math.max(...array) 방식은 10년치 일봉 데이터(2500개 이상)가 유입되었을 때 브라우저의 Call Stack 용량을 초과하여 프로그램이 비정상 종료(Maximum call stack size exceeded)되는 취약점이 있었습니다.")
    add_bullet(doc, "루프(reduce) 구현체로 변경: 이를 예방하기 위해 모든 최댓값/최솟값 연산 로직을 스프레드 연산자가 필요 없는 reduce 방식으로 전면 교체하여 연산의 신뢰성을 확보했습니다.")

    # ── 5. 의존성 ─────────────────────────────────────────────────────────────────
    add_h1(doc, "5. 의존성")
    add_table(doc,
        headers=["패키지 및 모듈", "용도 및 필요성"],
        rows=[
            ["FastAPI / Pydantic", "백엔드 API 파라미터 타입 유효성 검증 (models/market.py)"],
            ["httpx", "Yahoo Finance 서버로부터 금융 시장 일봉 차트 정보 조회"],
            ["React 18 / TypeScript", "프론트엔드 컴포넌트 렌더링 및 휠/드래그 터치 이벤트 바인딩 제어"],
            ["vitest / pytest", "프론트엔드 컴포넌트 상호작용 및 백엔드 라우터 통합 비즈니스 로직 테스트 실행 환경"]
        ]
    )

    # ── 6. 테스트 현황 ────────────────────────────────────────────────────────────
    add_h1(doc, "6. 테스트 현황")
    add_table(doc,
        headers=["테스트 파일 경로", "주요 검증 영역", "최종 상태"],
        rows=[
            ["tests/backend/test_yahoo_finance_provider.py", "신규 4개 기간의 파라미터 값 매핑 및 반환 검증", "PASS"],
            ["tests/backend/test_routes.py", "잘못된 기간 거부(422) 및 정상 기간 허용 검증, 기본값 1m 확인", "PASS"],
            ["tests/frontend/StockChart.test.tsx", "8개 버튼 클릭 이벤트 전달, 마우스 휠 줌인/줌아웃 visible 개수 및 미니맵 온오프, 드래그 이동에 따른 오버레이 연동, 엣지 케이스(단일 데이터, null) 방어 검증", "PASS"]
        ]
    )
    add_paragraph(doc, "모든 테스트 실행 환경에서 에러 및 경고 없이 안정적으로 빌드가 완료되는 것을 백엔드 pytest 및 프론트엔드 vitest 도구를 활용해 검증 완료했습니다.")

    # ── 7. 알려진 한계 및 추후 개선 ──────────────────────────────────────────────
    add_h1(doc, "7. 알려진 한계 및 추후 개선")
    add_bullet(doc, "전체 가시 범위의 SVG 렌더링 성능: 10Y 등의 기간을 선택하여 전체를 축소한 경우에는 전체 2500개 가량의 캔들 엘리먼트가 브라우저 DOM에 직접 등록되므로 모바일 환경에서 렌더링 지연이 생길 가능성이 남아 있습니다. 향후 대안으로 Canvas 엘리먼트 방식의 렌더링 구조로의 점진적 마이그레이션이 논의될 수 있습니다.")
    add_bullet(doc, "미니맵 직접 제어 기능의 부재: 현재 미니맵은 전체 흐름 오버레이 및 뷰포트 상태의 동기화 정보만을 조건부 렌더링하며, 사용자가 미니맵 내부를 직접 클릭하거나 드래그하여 차트를 이동하는 편의 기능은 제공되지 않습니다. 향후 사용자 경험 개선을 위해 미니맵 내부 마우스 위치 연산 이벤트를 연동하여 뷰포트 패닝을 트리거하는 보완을 수행할 수 있습니다.")

    # ── 저장 ──────────────────────────────────────────────────────────────────────
    os.makedirs(".ai/docs", exist_ok=True)
    doc.save(".ai/docs/03-project-chart-event_명세서.docx")
    print("성공적으로 워드 명세서 파일을 생성했습니다: .ai/docs/03-project-chart-event_명세서.docx")

if __name__ == "__main__":
    build_docx()
