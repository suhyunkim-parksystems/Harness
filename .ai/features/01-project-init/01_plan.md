# 01_plan - 01-project-init

작성: Antigravity
일시: 2026-06-04

## 기능 목표
- React 프론트엔드와 FastAPI 백엔드 기반의 주식 및 환율 대시보드 초기 프로젝트 구조와 동작을 설계한다.
- 미국, 한국, 기타 주요국의 대표지수와 주요 환율을 무료 API를 사용하여 한눈에 볼 수 있도록 구성하며, 개별 항목 실패 처리 및 자동/수동 갱신 기능을 설계한다.

## 구현 접근 방식
- **백엔드 (FastAPI)**:
  - `src/backend`에 위치하며, FastAPI 프레임워크를 사용한다. 
  - 모듈성과 확장성을 고려하여 라우터(`routes.py`), 서비스 레이어(`market_service.py`), 캐시 레이어(`cache.py`), 데이터 공급자 어댑터(`stooq.py`, `frankfurter.py`), 데이터 모델(`market.py`)로 명확히 분리한다.
  - 데이터 공급은 Stooq CSV와 Frankfurter v2 API를 사용하며, 외부 API 장애 및 제한(Rate Limit)에 대비하여 30초 TTL을 가진 인메모리 캐시를 기본으로 구현한다. 캐시 실패 시 직전 캐시 데이터가 존재하면 stale 상태로 서빙하여 회복탄력성을 높인다.
- **프론트엔드 (React)**:
  - `src/frontend`에 위치하며, Vite와 TypeScript를 빌드 도구로 채택한다.
  - 사용자는 60초 자동 새로고침(Toggle 가능) 및 수동 새로고침 기능을 사용할 수 있다.
  - UI는 현대적인 다크 모드 스타일의 카드 및 표 형태로 구성하며, 각 항목의 값, 변동값, 변동률, 기준 시각, 데이터 소스, 상태 배지(`ok`, `stale`, `unavailable`)를 일관성 있게 보여준다.
- **프로세스 관리 (.bat)**:
  - Windows CMD 환경에서 백엔드와 프론트엔드를 동시 구동하는 `src/start-dashboard.bat`와 안전하게 프로세스를 중단하는 `src/stop-dashboard.bat`를 작성한다.
  - 시작 시 실행 도구(Python, Node, npm) 및 포트 점유 여부를 검사하고, PID 파일을 생성하여 안전하고 고유한 종료 경로를 확보한다.

## 검토한 대안
- **대안 1: 단일 모놀리식 백엔드 파일 구조**
  - 장점: 빠른 초기 구현이 가능함.
  - 단점: 코드 복잡도가 올라가고, 외부 API 실패 및 캐싱 로직이 라우터와 섞여 유지보수가 어려움. 서비스 레이어를 분리하라는 프로젝트 계약의 요구사항을 위배함.
  - 채택하지 않은 이유: 유지보수 편의성과 프로젝트 계약 준수를 위해 채택하지 않음.
- **대안 2: Stooq 단독 사용**
  - 장점: 지수와 환율을 하나의 데이터 공급자로 통합하여 단순함.
  - 단점: Stooq의 간헐적인 미응답 및 환율 데이터 누락 위험이 존재할 때 대체 경로가 없음.
  - 채택하지 않은 이유: 환율 정보에 대해 Frankfurter v2 API를 보조(fallback) 공급자로 사용해 데이터 신뢰성을 보완하고자 제외함.

## 변경 파일 계획
- `src/backend/requirements.txt` (신규): `fastapi`, `uvicorn`, `httpx`, `pydantic`, `pytest`, `pytest-asyncio` 등 필요한 Python 패키지를 기재한다.
- `src/backend/app/__init__.py` (신규): 패키지 초기화 파일.
- `src/backend/app/main.py` (신규): FastAPI 앱 생성 및 CORS 설정, 라우터 등록.
- `src/backend/app/config.py` (신규): 개발 및 서버 실행용 설정 변수 관리 (`PORT`, `CORS_ORIGINS`, `CACHE_TTL`).
- `src/backend/app/models/market.py` (신규): `MarketItem` 및 `MarketSummary` 규격을 정의하는 Pydantic 스키마 정의.
- `src/backend/app/providers/symbols.py` (신규): 지수/환율 기본 심볼 및 표시 정보 관리.
- `src/backend/app/providers/stooq.py` (신규): Stooq CSV API 연동 어댑터 구현.
- `src/backend/app/providers/frankfurter.py` (신규): Frankfurter API 연동 어댑터 구현.
- `src/backend/app/services/cache.py` (신규): 30초 TTL 인메모리 캐시 서비스 구현.
- `src/backend/app/services/market_service.py` (신규): 공급자 데이터를 호출, 통합하고 캐싱을 처리하는 서비스 클래스.
- `src/backend/app/api/routes.py` (신규): `/api/health`, `/api/markets/summary`, `/api/markets/indices`, `/api/markets/exchange-rates` 라우터 구현.
- `src/frontend/package.json` (신규): React 및 Vite 개발/테스트 의존성, 실행 스크립트 정의.
- `src/frontend/tsconfig.json` (신규): TypeScript 컴파일 옵션 설정.
- `src/frontend/vite.config.ts` (신규): Vite 및 프록시 설정, Vitest 테스트 환경 구성.
- `src/frontend/index.html` (신규): HTML 마운트 페이지 정의.
- `src/frontend/src/main.tsx` (신규): React 진입점.
- `src/frontend/src/App.tsx` (신규): 메인 대시보드 뷰 및 갱신 상태 훅 적용.
- `src/frontend/src/App.css` (신규): 다크 테마 및 컴포넌트 스타일 정의.
- `src/frontend/src/api/markets.ts` (신규): 백엔드 API와의 통신을 관리하는 fetch 모듈.
- `src/frontend/src/types/market.ts` (신규): 프론트엔드용 TypeScript 타입 정의.
- `src/frontend/src/hooks/useMarketSummary.ts` (신규): 자동 갱신 및 상태 관리용 커스텀 훅.
- `src/frontend/src/components/DashboardHeader.tsx` (신규): 갱신 시간, 토글, 새로고침 등 제어판 영역.
- `src/frontend/src/components/MarketSection.tsx` (신규): 지수 및 환율의 카테고리별 그리드 컨테이너.
- `src/frontend/src/components/MarketTable.tsx` (신규): 시세 데이터를 렌더링하는 데이터 테이블.
- `src/frontend/src/components/StatusBadge.tsx` (신규): 시세 정보 상태 배지 컴포넌트.
- `src/start-dashboard.bat` (신규): 의존성 설치 유무 검사, 백엔드/프론트엔드 실행 및 PID 파일 기록.
- `src/stop-dashboard.bat` (신규): PID 파일 및 포트 기반 프로세스 안전 종료.
- `tests/backend/conftest.py` (신규): 백엔드 테스트를 위한 Pytest 공통 Fixture 정의.
- `tests/backend/test_stooq_provider.py` (신규): Stooq 데이터 정규화 및 실패 테스트.
- `tests/backend/test_frankfurter_provider.py` (신규): Frankfurter API 연동 및 실패 처리 테스트.
- `tests/backend/test_market_service.py` (신규): 서비스 레이어, 캐시 동작 검증 테스트.
- `tests/backend/test_routes.py` (신규): 라우터 API 엔드포인트 응답 형식 및 상태 코드 테스트.
- `tests/frontend/setupTests.ts` (신규): Vitest React 테스팅 라이브러리 연동 및 Mock API 초기화.
- `tests/frontend/App.test.tsx` (신규): 대시보드 주요 컴포넌트 정상 로딩 및 실패 처리 화면 테스트.
- `tests/frontend/useMarketSummary.test.tsx` (신규): 새로고침 및 타이머 훅 동작 테스트.
- `tests/scripts/test_batch_files.py` (신규): 배치파일 존재 여부 및 스모크 테스트.

## 데이터 / 제어 흐름
- 사용자가 프론트엔드 대시보드를 방문하면 API 요청이 전송된다.
- 백엔드에서는 캐싱된 데이터가 유효하면 즉시 캐시 데이터를 전달한다.
- 캐시 미스 또는 만료 시, 각 데이터 공급자 어댑터를 비동기(`asyncio.gather`)로 병렬 호출하여 속도를 최적화한다.
- 개별 공급자 호출 실패 시에도 전체 서비스가 실패하지 않도록 예외 처리를 거치고, 최종적으로 규격화된 `MarketSummary` JSON 형태로 가공하여 반환한다.

```text
[ React Dashboard UI ]
         │ (GET /api/markets/summary)
         ▼
[ FastAPI App (main.py / routes.py) ]
         │
         ▼
[ MarketService (market_service.py) ] ─── (HIT) ───► [ Memory Cache ]
         │ (MISS)
         ▼
 ┌───────┴────────────────────────────────────┐
 │  (asyncio.gather)                          │
 ▼                                            ▼
[ StooqProvider ]                     [ FrankfurterProvider ]
 (Stooq CSV API)                       (Frankfurter v2 API)
```

## 구현 단계 분할
1. **1단계: 백엔드 아키텍처 및 라우터 뼈대 설정**
   - 파일: `requirements.txt`, `app/main.py`, `app/api/routes.py`, `tests/backend/test_routes.py` 등
   - 완료 기준: FastAPI가 구동되고 `/api/health` 및 각 목업 API 라우트가 정상 응답할 때.
2. **2단계: 데이터 정규화 스키마 및 공급자 어댑터 개발**
   - 파일: `app/models/market.py`, `app/providers/**`, `tests/backend/test_*_provider.py`
   - 완료 기준: Stooq 및 Frankfurter 어댑터의 비동기 연동 및 정상/에러 파싱 로직 테스트 통과 시.
3. **3단계: 서비스 레이어 및 TTL 캐시 구현**
   - 파일: `app/services/**`, `tests/backend/test_market_service.py`
   - 완료 기준: 30초 TTL 캐싱이 작동하며 공급자 병렬 연동 및 예외 처리 로직의 테스트 통과 시.
4. **4단계: 프론트엔드 프로젝트 초기화 및 API 연동부 개발**
   - 파일: `package.json`, `tsconfig.json`, `vite.config.ts`, `src/api/**`, `src/types/**`
   - 완료 기준: Vite 개발 서버 구성 완료 및 브라우저/Vitest에서 API 요청을 목업으로 처리 가능할 때.
5. **5단계: 대시보드 컴포넌트 및 상태 제어 개발**
   - 파일: `src/App.tsx`, `src/hooks/**`, `src/components/**`, `tests/frontend/**`
   - 완료 기준: 다크 테마 UI 적용 및 자동/수동 갱신, 부분/전체 에러 UI 테스트가 통과될 때.
6. **6단계: Windows 배치파일 구현 및 스모크 테스트**
   - 파일: `src/start-dashboard.bat`, `src/stop-dashboard.bat`, `tests/scripts/test_batch_files.py`
   - 완료 기준: 안전한 실행 및 PID 기반 프로세스 종료 및 스모크 테스트가 검증되었을 때.

## 위험 구간
- **위험 항목 1: Windows 환경에서 포트 충돌 및 프로세스 종료 실패**
  - 상세 내용: 기본 포트(8000, 5173)를 다른 프로세스가 이미 사용하고 있다면 오류가 발생할 수 있다. 프로세스를 강제 종료할 때 엉뚱한 로컬 프로세스가 종료될 위험이 있다.
  - 완화 방안: `start-dashboard.bat`에서 `netstat`을 이용해 대상 포트의 점유 여부를 사전 체크하여 점유 시 시작하지 않고 에러를 반환한다. 구동 시 PID를 파일로 기록해 `stop-dashboard.bat`에서 해당 PID만 `taskkill`하도록 조치하고, 포트 기준 종료는 보조 수단으로만 엄격하게 제한한다.
- **위험 항목 2: 무료 데이터 API의 Rate Limit 혹은 접속 불안정성**
  - 상세 내용: 무료 API의 오버헤드나 순간적인 다중 요청은 429(Too Many Requests) 또는 일시적 IP 블록을 유발한다.
  - 완화 방안: 백엔드에 30초 인메모리 TTL 캐시를 적용하여 외부 호출 횟수를 엄격히 제어한다. 만일 API 응답이 실패하거나 점검 시간인 경우, 최근 캐싱된 데이터(stale)가 존재한다면 배지를 `stale`로 낮추고 값을 반환한다.
- **위험 항목 3: 가상환경 및 Node 패키지 자동 설치 오류**
  - 상세 내용: 로컬 머신에 Python 또는 Node/npm이 PATH에 등록되어 있지 않거나 권한이 부족하여 자동 의존성 설치가 실패하고 먹통이 될 수 있다.
  - 완화 방안: 배치파일 도입부에 `python --version`, `node --version`, `npm --version` 명령어가 정상적으로 실행되는지 검사하고 미설치 상태라면 사용자에게 명확히 알린다. 설치 중 에러 발생 시 진행을 중단한다.

## 호환성 검토
- **보존해야 할 기존 인터페이스**: 없음 (새 프로젝트 초기화 단계이므로 기존 소스코드가 존재하지 않는다.)
- **하위 호환성 위험**: 없음.
- **breaking change 필요 여부**: 없음.

## 새 의존성
- **백엔드**:
  - `fastapi`, `uvicorn` (ASGI 서버)
  - `httpx` (비동기 HTTP 요청)
  - `pydantic` (데이터 유효성 검사 및 정규화)
  - `pytest`, `pytest-asyncio` (비동기 테스트 도구)
- **프론트엔드**:
  - `react`, `react-dom` (프론트엔드 핵심 라이브러리)
  - `vite`, `typescript`, `@vitejs/plugin-react` (빌드 및 프레임워크 플러그인)
  - `lucide-react` (아이콘 라이브러리)
  - `vitest`, `jsdom`, `@testing-library/react` (컴포넌트 및 단위 테스트 도구)

## 테스트 전략
- **백엔드**:
  - 외부 네트워크에 의존하지 않도록 `httpx.AsyncClient` 호출 부에 대한 mock 처리를 구현한다.
  - Stooq CSV 데이터 파싱(정상 값, `N/D`, 변동 금액 계산 등) 및 Frankfurter JSON 파싱 테스트 수행.
  - 서비스 레이어 캐싱 히트/미스 및 부분 실패 전파 테스트 수행.
  - API 라우터 요청에 대한 적절한 JSON 반환 형식 검증.
- **프론트엔드**:
  - Vitest와 React Testing Library를 사용해 화면 컴포넌트 단위 테스트를 수행한다.
  - 로딩 상태, 성공적으로 가공된 데이터 리스트 렌더링, 부분 실패(`unavailable` / `stale` 배지 노출) 등의 상태 테스트.
  - 자동 갱신 타이머 작동 및 수동 새로고침 클릭 시 호출 테스트.
- **스크립트**:
  - 배치파일 존재 여부, 지정 포트 충돌 대책 메시지 출력 구조 등 스모크 검증을 수행한다.

## 롤백 / 복구 방향
- 모든 작업이 `src/`와 `tests/` 하위의 신규 파일 생성에 머무르므로, 배포 또는 구동 실패 시 해당 신규 디렉토리와 파일을 삭제하여 이전 HEAD 상태로 완전히 롤백할 수 있다.

## 실행 승인
- risk_level: medium
- human_gate_required: false
- human_gate_reason: 없음. (스펙과 기술 스택이 확정되었고, 기존 파일 영향도가 없으며 포트 및 프로세스 안전 종료 등의 위험 완화 장치가 배치파일에 설계되었으므로 PASS 가능함.)
- approval_required_before_develop: false

## 스펙 모호점 처리
- **기타 주요국 지수의 API 응답 부재 대처**: `^NKX`(Nikkei), `^UKX`(FTSE) 등 Stooq에 매핑되는 심볼들을 제공하나, 휴일 혹은 무료 계정 만료로 응답이 비어있으면 `status: "unavailable"`로 정규화해 프론트엔드에서 회색 배지로 표시한다.
- **환율 변동성**: Stooq에서 전일 종가(Prev)를 획득할 수 없는 경우(예: Frankfurter fallback 시), 변동률은 `null`로 제공하며 UI에는 현재값만 표시하고 상태 배지를 `stale`로 지정한다.

## Git 기준점
- base_commit: e8b9a32558dcc9423e1bc036d440d76c7d4c24c4
- diff_base_command: `git diff e8b9a32558dcc9423e1bc036d440d76c7d4c24c4`

## 사용자 확인 사항
- 없음 (defaults_mode: true에 따라 기본 권장안을 채택함.)

## 단계 결과
- status: PASS
- next_stage: 02_develop
- human_gate_required: false
- blocking_reason: 없음
- risk_level: medium
- produced_files:
  - .ai/features/01-project-init/01_plan.md
  - .ai/features/01-project-init/01_plan.result.json
- changed_files:
  - .ai/features/01-project-init/01_plan.md
  - .ai/features/01-project-init/01_plan.result.json
- harness_commit_required: true
- commit_created_by_model: false
- commit_message_suggestion: "docs: 주식 대시보드 프로젝트 초기화 구현 계획 수립"
- model_mismatch: false
- actual_model: Antigravity
