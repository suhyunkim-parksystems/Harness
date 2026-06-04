# 00_spec - 01-project-init

작성: Codex
일시: 2026-06-04

## 기능 목표
- React 프론트엔드와 FastAPI 백엔드로 구성된 주식/환율 대시보드 프로젝트의 초기 구조와 동작 범위를 확정한다.
- 사용자는 한 화면에서 미국 대표지수, 한국 대표지수, 기타 주요국 대표지수, 주요 환율 정보를 무료 데이터 소스 기반 최신 시세로 확인할 수 있어야 한다.

## 기능명
- feature_name: 01-project-init
- naming_reason: 하네스에서 `feature_name_locked: true`로 제공한 기능명을 변경하지 않는 것이 필수 조건이므로 기존 slug를 유지한다.

## 구체적 요구사항
- `src/backend` 아래에 FastAPI 백엔드를 구성한다.
- `src/frontend` 아래에 React 프론트엔드를 구성한다.
- `src/start-dashboard.bat` 파일 하나로 백엔드와 프론트엔드를 함께 실행할 수 있어야 한다.
- `src/stop-dashboard.bat` 파일로 이미 백그라운드 또는 별도 창에서 실행 중인 백엔드와 프론트엔드 프로세스를 종료할 수 있어야 한다.
- 실행 스크립트는 현재 운영체제인 Windows 환경을 기준으로 `.bat` 파일로 제공한다.
- 기본 개발 포트는 백엔드 `8000`, 프론트엔드 `5173`으로 한다. 포트는 환경변수로 변경 가능해야 한다.
- 백엔드는 외부 무료 데이터 소스를 호출하는 서비스 레이어를 둔다.
- 백엔드는 최소한 다음 API를 제공한다.
  - `GET /api/health`: 서버 상태와 데이터 공급자 설정 상태를 반환한다.
  - `GET /api/markets/summary`: 지수와 환율 데이터를 한 번에 묶어 반환한다.
  - `GET /api/markets/indices`: 지수 데이터만 반환한다.
  - `GET /api/markets/exchange-rates`: 환율 데이터만 반환한다.
- 프론트엔드는 `/api/markets/summary`를 호출해 대시보드 첫 화면에 모든 정보를 표시한다.
- 대시보드는 다음 구역을 한눈에 보여야 한다.
  - 미국 대표지수: S&P 500, Nasdaq 100, Dow Jones Industrial Average를 기본값으로 표시한다.
  - 한국 대표지수: KOSPI를 필수 기본값으로 표시하고, 무료 데이터 소스에서 유효한 심볼이 확인되는 경우 KOSDAQ 또는 KOSPI 200을 추가 표시한다.
  - 기타 주요국 대표지수: Nikkei 225, DAX, FTSE 100, Shanghai Composite, Hang Seng을 기본 후보로 둔다. 무료 소스에서 응답이 없는 지수는 개별 항목을 `unavailable`로 표시한다.
  - 환율정보: USD/KRW, USD/JPY, EUR/USD, USD/CNY, GBP/USD를 기본값으로 표시한다.
- 각 시세 항목은 현재값, 전일 대비 또는 세션 대비 변동값, 변동률, 기준 시각, 데이터 소스명, 데이터 상태를 포함해야 한다.
- 무료 API만 사용한다. 기본 구현은 API 키가 필요 없는 무료 소스를 우선 사용한다.
- 데이터 공급자는 무료 제공 범위 안에서 가능한 최신값을 사용한다. 무료 소스의 지연, 장 마감 시각, 휴장일 때문에 거래소급 완전 실시간이 보장되지 않을 수 있으므로 UI에 `asOf`와 `source`를 반드시 표시한다.
- 외부 API 응답 실패, 타임아웃, `N/D` 같은 무효 값은 전체 대시보드를 실패시키지 않고 해당 항목만 `unavailable` 또는 `stale` 상태로 표시한다.
- 백엔드는 동일 요청의 중복 외부 호출을 줄이기 위해 짧은 TTL 캐시를 둘 수 있다. 기본 TTL은 30초로 한다.
- 프론트엔드는 초기 로딩, 부분 실패, 전체 실패, 새로고침 중 상태를 구분해 표시한다.
- 프론트엔드는 수동 새로고침 버튼을 제공한다. 자동 갱신은 기본 60초 주기로 하되 사용자가 화면에서 끄거나 켤 수 있어야 한다.
- 테스트 코드는 반드시 루트 `tests/` 아래에 둔다.
- 백엔드 테스트는 서비스 레이어, 응답 정규화, FastAPI 라우트, 외부 API 실패 처리, 캐시 동작을 포함한다.
- 프론트엔드 테스트는 데이터 로딩, 구역별 렌더링, 부분 실패 표시, 새로고침 동작을 포함한다.
- 배치파일 테스트 또는 스모크 검증은 start/stop 파일 존재, 주요 명령 문자열, 포트/프로세스 종료 전략을 확인한다.

## 이번 범위에서 제외하는 것
- 사용자 인증/인가: 대시보드 초기 기능에는 로그인 요구가 없다.
- 결제 또는 유료 API 연동: 사용자가 과금을 원하지 않는다고 명시했다.
- 개인 관심종목, 포트폴리오, 주문/매매 기능: 이번 요구는 대표지수와 환율 조회에 한정된다.
- 데이터 영구 저장 DB: 실시간 조회형 대시보드가 목적이므로 초기 범위에서는 메모리 캐시만 사용한다.
- 모바일 앱 또는 데스크톱 설치 프로그램: React 웹 화면과 Windows 실행 배치파일만 범위에 포함한다.
- 배포용 Docker, 클라우드 배포, CI 구성: 로컬 개발 실행과 테스트 가능 상태를 먼저 만든다.

## 입력과 출력
- 사용자 입력:
  - 프론트엔드에서 수동 새로고침 버튼 클릭
  - 자동 갱신 on/off 설정
  - 선택적으로 포트 환경변수 `BACKEND_PORT`, `FRONTEND_PORT`
- 백엔드 외부 입력:
  - 무료 시장 데이터 HTTP 응답
  - 무료 환율 데이터 HTTP 응답
- 백엔드 출력:
  - JSON 응답
  - 대표 응답 필드: `id`, `name`, `category`, `region`, `symbol`, `value`, `change`, `changePercent`, `currency`, `asOf`, `source`, `status`, `errorMessage`
- 프론트엔드 출력:
  - 지수/환율 카드 또는 표 형태의 대시보드
  - 데이터 기준 시각과 소스 표시
  - 로딩, 오류, 부분 오류, 갱신 상태 표시
- 비정상 입력 처리:
  - 외부 API 타임아웃은 항목별 실패로 변환한다.
  - 숫자 파싱 실패, 빈 응답, `N/D` 값은 `unavailable`로 변환한다.
  - 백엔드 전체 장애는 프론트엔드에서 재시도 가능한 오류 상태로 표시한다.

## 기존 코드 영향
- 현재 저장소에는 애플리케이션용 `src/`와 `tests/`가 없다.
- 다음 단계 구현에서는 새 파일을 주로 추가한다.
- 수정 예상 경로:
  - `src/backend/**`
  - `src/frontend/**`
  - `src/start-dashboard.bat`
  - `src/stop-dashboard.bat`
  - `tests/backend/**`
  - `tests/frontend/**`
  - `tests/scripts/**`
- 사용할 기존 모듈/유틸은 없다.
- `.ai/**`, `presets/**`, 하네스 자체 파일은 기능 구현 대상이 아니다.
- 루트에 `requirements.txt`, `package.json`, 실행 스크립트를 만들지 않는다. 필요한 보조 파일은 `src/` 또는 `tests/` 아래에 둔다.

## 기술적 제약
- 백엔드 프레임워크는 FastAPI를 사용한다.
- 백엔드 HTTP 클라이언트는 비동기 호출과 타임아웃 처리가 가능한 라이브러리를 사용한다.
- 백엔드 구조는 라우터, 서비스 레이어, 데이터 공급자 어댑터, 정규화 모델을 분리한다.
- 프론트엔드는 React를 사용한다.
- 프론트엔드 빌드 도구는 Vite + TypeScript를 기본값으로 한다. 이유는 React 로컬 개발 서버, 테스트, 타입 안정성 구성이 단순하기 때문이다.
- 프론트엔드 상태 관리는 초기 범위에서 React 내장 상태와 훅을 우선한다. 전역 상태 라이브러리는 추가하지 않는다.
- 무료 데이터 소스 기본 결정:
  - 지수와 실시간성에 가까운 환율 최신값은 Stooq의 무료 quote CSV 엔드포인트를 우선 검토한다.
  - 환율 일일 기준값 또는 보조 검증용으로 Frankfurter의 무료 환율 API를 사용할 수 있다.
  - API 키가 필요한 무료 티어 서비스는 기본값으로 사용하지 않는다. 구현 단계에서 꼭 필요해지면 무료 키 필요성과 대체안을 별도 기록한다.
- 데이터 소스 참고:
  - Stooq: https://stooq.com/
  - Frankfurter: https://frankfurter.dev/
- 무료 API의 약관, 지연 시간, 제공 심볼은 변경될 수 있으므로 공급자 어댑터를 분리하고 테스트에서는 외부 네트워크를 mock 처리한다.
- 테스트는 외부 네트워크에 의존하지 않아야 한다.
- Windows 실행을 우선 지원한다. Linux/macOS용 실행 스크립트는 이번 범위에서 제외한다.

## 기본 결정 및 근거
- `NEEDS_USER` 없이 진행: `defaults_mode: true`이고 무료·무인증 소스를 우선하는 기본안으로 구현 방향을 정할 수 있다.
- 완전 실시간 대신 무료 최신 시세로 정의: 무료 API만으로 모든 국가 지수의 거래소급 실시간성을 보장하기 어렵기 때문에, 각 항목의 기준 시각과 소스를 표시하는 방식으로 검증 가능성을 확보한다.
- React + Vite + TypeScript 선택: 새 프로젝트 초기화에 적합하고 테스트 도구 구성이 단순하다.
- FastAPI 서비스 레이어 분리: 프로젝트 계약의 서비스 레이어 요구와 외부 API 실패 처리 요구를 충족한다.
- `.bat` 실행/종료 스크립트 선택: 사용자의 운영체제가 Windows이고 배치파일을 명시적으로 요구했다.
- 테스트 위치는 루트 `tests/`로 고정: 프로젝트 계약상 새 테스트 파일을 `src/` 아래에 만들 수 없다.

## 위험도 및 게이트
- risk_level: high
- human_gate_required: true
- human_gate_reason: 새 React/FastAPI 프로젝트 구조, 외부 무료 데이터 소스 연동, 새 의존성, Windows 프로세스 실행/종료 스크립트가 포함되어 사용자 승인 게이트가 필요하다.

## 사용자 확인 사항
- 별도 질문 없음.
- 기본값으로 확정한 사항:
  - 무료·무인증 데이터 소스를 우선한다.
  - 무료 소스의 지연 가능성을 UI에 표시한다.
  - 기본 지수/환율 목록은 위 요구사항의 후보 목록을 사용한다.
  - Windows `.bat` 파일로 시작/종료를 제공한다.

## 단계 결과
- status: PASS
- next_stage: 01_plan
- human_gate_required: true
- blocking_reason: 없음
- risk_level: high
- produced_files:
  - .ai/features/01-project-init/00_spec.md
  - .ai/features/01-project-init/00_spec.result.json
- changed_files:
  - .ai/features/01-project-init/00_spec.md
  - .ai/features/01-project-init/00_spec.result.json
- harness_commit_required: true
- commit_created_by_model: false
- commit_message_suggestion: "docs: 주식 대시보드 초기 스펙 작성"
- model_mismatch: false
- actual_model: Codex
