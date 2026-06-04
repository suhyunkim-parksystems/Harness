# 02_dev - 01-project-init

작성: Codex
일시: 2026-06-04

## 기능 목표
- React 프론트엔드와 FastAPI 백엔드로 미국/한국/기타국 대표지수와 주요 환율을 한 화면에서 조회하는 주식·환율 대시보드 초기 구현을 완료했다.
- 무료·무인증 데이터 소스(Stooq, Frankfurter)를 사용하고, Windows용 start/stop 배치파일과 테스트 코드를 함께 제공했다.

## 변경 파일
- .ai/features/01-project-init/00_spec.md (입력 / 변경 금지)
- .ai/features/01-project-init/01_plan.md (입력 / 변경 금지)
- .ai/features/01-project-init/02_dev.md (신규)
- .ai/features/01-project-init/02_dev.result.json (신규)
- src/.gitignore (신규)
- src/start-dashboard.bat (신규)
- src/stop-dashboard.bat (신규)
- src/backend/.gitignore (신규)
- src/backend/requirements.txt (신규)
- src/backend/app/__init__.py (신규)
- src/backend/app/main.py (신규)
- src/backend/app/config.py (신규)
- src/backend/app/api/__init__.py (신규)
- src/backend/app/api/routes.py (신규)
- src/backend/app/models/__init__.py (신규)
- src/backend/app/models/market.py (신규)
- src/backend/app/providers/__init__.py (신규)
- src/backend/app/providers/symbols.py (신규)
- src/backend/app/providers/stooq.py (신규)
- src/backend/app/providers/frankfurter.py (신규)
- src/backend/app/services/__init__.py (신규)
- src/backend/app/services/cache.py (신규)
- src/backend/app/services/market_service.py (신규)
- src/frontend/.gitignore (신규)
- src/frontend/package.json (신규)
- src/frontend/package-lock.json (신규)
- src/frontend/tsconfig.json (신규)
- src/frontend/vite.config.ts (신규)
- src/frontend/index.html (신규)
- src/frontend/src/main.tsx (신규)
- src/frontend/src/App.tsx (신규)
- src/frontend/src/App.css (신규)
- src/frontend/src/api/markets.ts (신규)
- src/frontend/src/types/market.ts (신규)
- src/frontend/src/hooks/useMarketSummary.ts (신규)
- src/frontend/src/components/DashboardHeader.tsx (신규)
- src/frontend/src/components/MarketSection.tsx (신규)
- src/frontend/src/components/MarketTable.tsx (신규)
- src/frontend/src/components/StatusBadge.tsx (신규)
- tests/.gitignore (신규)
- tests/backend/conftest.py (신규)
- tests/backend/test_stooq_provider.py (신규)
- tests/backend/test_frankfurter_provider.py (신규)
- tests/backend/test_market_service.py (신규)
- tests/backend/test_routes.py (신규)
- tests/frontend/setupTests.ts (신규)
- tests/frontend/App.test.tsx (신규)
- tests/frontend/useMarketSummary.test.tsx (신규)
- tests/scripts/test_batch_files.py (신규)

## 구현 내용
- FastAPI 백엔드에 `/api/health`, `/api/markets/summary`, `/api/markets/indices`, `/api/markets/exchange-rates` 라우트를 구현했다.
- Stooq CSV quote API에서 지수와 환율 값을 받아 `Close - Prev` 기준 변동값과 변동률을 계산하고, 무효값은 항목별 `unavailable`로 정규화했다.
- Frankfurter 최신 환율 API를 Stooq 환율 실패 시 fallback으로 사용하며, 일간 기준 fallback 값은 `stale`로 표시한다.
- 30초 TTL 인메모리 캐시를 구현했고, refresh 실패 시 직전 캐시가 있으면 항목 상태를 `stale`로 바꿔 반환한다.
- React/Vite/TypeScript 프론트엔드에 구역별 대시보드, 상태 배지, 수동 새로고침, 60초 자동 새로고침 토글, 로딩/전체 실패/부분 실패 표시를 구현했다.
- `src/start-dashboard.bat`은 Python/Node/npm 확인, 백엔드 venv 생성, 의존성 설치, 프론트엔드 npm install, 포트 점검, PID 기록 후 서버를 실행한다.
- `src/stop-dashboard.bat`은 PID 파일 기반 종료를 우선 사용하고, 명령줄이 개발 서버와 일치하는 경우에만 포트 기반 보조 종료를 수행한다.

## 왜 이렇게 구현했는가
- 무료·무인증 요구를 만족하기 위해 API 키가 필요 없는 Stooq와 Frankfurter를 사용했다.
- 무료 시장 데이터는 거래소별 실시간성이 다르므로 `asOf`, `source`, `status`를 각 항목에 명시해 사용자가 데이터 상태를 확인할 수 있게 했다.
- 공급자 어댑터, 서비스 레이어, 캐시, 라우트를 분리해 향후 무료 공급자 교체나 보강을 쉽게 했다.
- Vite 테스트가 루트 `tests/` 경로의 테스트 파일을 읽으면서 `src/frontend/node_modules`를 해석해야 하므로, `vite.config.ts`에 테스트용 exact alias를 추가했다.
- `package-lock.json`은 재현 가능한 프론트엔드 설치를 위해 `src/frontend` 아래에 포함했다.
- `.gitignore`는 실행/테스트 중 생기는 `.venv`, `node_modules`, `dist`, PID/로그, 빌드 정보가 커밋 범위에 섞이지 않도록 `src/`와 `tests/` 하위에만 추가했다.

## 호환성 준수
- 01_plan.md의 호환성 유지 전략 반영 내용: 기존 프로덕션 코드와 공개 API가 없는 초기 구현이므로 새 구조를 계획 파일의 파일 배치에 맞춰 추가했다.
- 보존한 기존 인터페이스/데이터 포맷/설정 키: 기존 인터페이스 없음. 새 JSON 응답은 요구사항의 `changePercent`, `asOf`, `errorMessage`, `exchangeRates`, `cacheTtlSeconds` camelCase 키를 유지했다.
- breaking change 발생 여부: 없음
- 계획에 없던 호환성 영향과 처리: 없음

## 새로 추가한 의존성
- backend: `fastapi`, `uvicorn`, `httpx`, `pydantic`, `pytest`, `pytest-asyncio`
- frontend: `react`, `react-dom`, `lucide-react`, `vite`, `typescript`, `@vitejs/plugin-react`, `vitest`, `jsdom`, `@testing-library/react`, `@types/react`, `@types/react-dom`
- 추가 이유: 01_plan.md의 FastAPI/React/Vite/테스트 전략 수행. `@types/*`는 TypeScript 빌드에 필요한 타입 패키지다.

## 테스트
- 작성한 테스트 파일:
  - tests/backend/test_stooq_provider.py
  - tests/backend/test_frankfurter_provider.py
  - tests/backend/test_market_service.py
  - tests/backend/test_routes.py
  - tests/frontend/App.test.tsx
  - tests/frontend/useMarketSummary.test.tsx
  - tests/scripts/test_batch_files.py
- 커버 범위:
  - Stooq CSV 파싱, `N/D`/무효값 무시, 변동값 계산
  - Frankfurter fallback 응답 정규화와 실패 흡수
  - 서비스 레이어 캐시 hit, 부분 실패, stale 캐시 fallback
  - FastAPI 라우트와 camelCase JSON 응답
  - React 로딩, 구역 렌더링, 부분 실패 표시, 수동 새로고침, 자동 새로고침 토글
  - start/stop 배치파일의 포트/PID/설치/종료 명령 구조
- 실행한 테스트 명령:
  - `python -m pytest -q tests/backend tests/scripts -p no:cacheprovider`
  - `npm test` (`src/frontend`)
  - `npm run build` (`src/frontend`)
  - `.\src\start-dashboard.bat`
  - `Invoke-WebRequest http://127.0.0.1:8000/api/health`
  - `Invoke-WebRequest http://127.0.0.1:5173`
  - `.\src\stop-dashboard.bat`
  - 백엔드 서비스 실제 공급자 통합 스니펫
- 테스트 실행 결과:
  - backend/scripts: 11 passed, Starlette `python_multipart` 관련 deprecation warning 1건
  - frontend: 6 passed
  - frontend build: 성공
  - start/stop 배치 검증: health 응답 200, frontend 응답 200, stop 후 8000/5173 포트 closed
  - 실제 공급자 통합: `{'status': 'ok', 'indices': 9, 'exchangeRates': 5, 'unavailable': 0}`
- 의도적으로 테스트하지 않은 부분:
  - 외부 API의 실시간 정확도는 무료 공급자의 현재 응답에 의존하므로 단위 테스트에서는 mock/fixture로 검증했다.
  - Browser 플러그인 렌더링 확인은 현재 세션에 사용 가능한 브라우저 대상이 없어 수행하지 못했다. HTTP 응답, Vitest 렌더링 테스트, Vite build로 대체 검증했다.

## 알려진 한계 / 추후 개선 사항
- Stooq/Frankfurter 무료 API는 거래소별 지연, 휴장일, 심볼 지원 변경이 있을 수 있다.
- Frankfurter fallback 환율은 일간 기준이므로 `stale`로 표시되며 전일 대비 변동값은 제공하지 않는다.
- 현재 캐시는 프로세스 메모리 기반이라 서버 재시작 시 초기화된다.
- Browser 플러그인 대상이 없는 환경에서는 실제 브라우저 스크린샷 검증이 불가하다.

## Git 정보
- base_commit: e8b9a32558dcc9423e1bc036d440d76c7d4c24c4
- harness_commit_required: true
- commit_created_by_model: false
- commit_message_suggestion: 01-project-init[20260604-214444][02_develop]
- commit_scope:
  - .ai/features/01-project-init/02_dev.md
  - .ai/features/01-project-init/02_dev.result.json
  - src/**
  - tests/**
- pre_commit_diff_command: git diff e8b9a32558dcc9423e1bc036d440d76c7d4c24c4
- changed_files:
  - .ai/features/01-project-init/02_dev.md
  - .ai/features/01-project-init/02_dev.result.json
  - src/.gitignore
  - src/start-dashboard.bat
  - src/stop-dashboard.bat
  - src/backend/.gitignore
  - src/backend/requirements.txt
  - src/backend/app/**
  - src/frontend/.gitignore
  - src/frontend/package.json
  - src/frontend/package-lock.json
  - src/frontend/tsconfig.json
  - src/frontend/vite.config.ts
  - src/frontend/index.html
  - src/frontend/src/**
  - tests/.gitignore
  - tests/backend/**
  - tests/frontend/**
  - tests/scripts/**
- harness_commit_blocking_reason: 없음

## 단계 결과
- status: PASS
- next_stage: 03_review
- human_gate_required: false
- blocking_reason: 없음
- risk_level: medium
- produced_files:
  - .ai/features/01-project-init/02_dev.md
  - .ai/features/01-project-init/02_dev.result.json
  - src/**
  - tests/**
- changed_files:
  - .ai/features/01-project-init/02_dev.md
  - .ai/features/01-project-init/02_dev.result.json
  - src/**
  - tests/**
- harness_commit_required: true
- commit_created_by_model: false
- commit_message_suggestion: 01-project-init[20260604-214444][02_develop]
- test_commands:
  - python -m pytest -q tests/backend tests/scripts -p no:cacheprovider
  - npm test (src/frontend)
  - npm run build (src/frontend)
  - .\src\start-dashboard.bat
  - .\src\stop-dashboard.bat
- model_mismatch: true
- actual_model: Codex
