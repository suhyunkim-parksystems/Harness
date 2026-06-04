# 04_fix - 01-project-init

작성: Codex
일시: 2026-06-04

## 입력으로 처리한 지적
- 03_review.md must_fix: 외부 API 통신 예외 발생 시 대시보드 API 전체가 503으로 실패할 수 있는 문제.
- 03_review.md should_consider: 공급자 HTTP timeout 기본값 8초 축소, 데이터가 없는 항목의 source를 `Stooq CSV` 고정 대신 `N/A`로 표시.
- 05_verify.md 실패 항목: 없음. 파일이 존재하지 않음.
- 05_verify.md가 추가한 테스트 파일: 없음.
- 하네스 검증 JSON: 없음. `.ai/runs/01-project-init/verification/latest.json`이 존재하지 않음.

## 수용한 항목
- 출처: 03_review
- severity: MAJOR
- 지적 내용 요약: Stooq 또는 Frankfurter 호출 예외가 `_fetch_summary` 밖으로 전파되어 캐시가 없는 최초 호출에서 전체 API가 503으로 실패할 수 있음.
- 수정한 파일과 변경 내용: `src/backend/app/services/market_service.py`에 공급자별 예외 격리 헬퍼를 추가하고, 실패한 공급자는 빈 결과로 처리해 나머지 데이터 처리를 계속하도록 변경. 전체 결과가 unavailable이고 stale 캐시가 있으면 기존 stale 캐시 반환 보장도 유지.
- 왜 수용했는가: 무료 외부 API는 실패 가능성이 높고, 프로젝트 계약상 외부 입력/네트워크 실패를 명시적으로 처리해야 하므로 실제 안정성 결함임.

- 출처: 03_review
- severity: MINOR
- 지적 내용 요약: 공급자 기본 timeout 8초가 대시보드 응답성에 비해 길다.
- 수정한 파일과 변경 내용: `src/backend/app/providers/stooq.py`, `src/backend/app/providers/frankfurter.py`의 기본 timeout을 4초로 조정. 회귀 방지를 위해 공급자 기본 timeout 테스트 추가.
- 왜 수용했는가: 3~5초 권장 범위 안에서 사용자 대기 시간을 줄이는 변경이며 기존 생성자 인자와 공개 API를 깨지 않음.

- 출처: 03_review
- severity: MINOR
- 지적 내용 요약: 데이터가 없는 unavailable 항목의 source가 `Stooq CSV`로 고정되어 실제 상태를 오해하게 함.
- 수정한 파일과 변경 내용: `src/backend/app/services/market_service.py`에서 unavailable 항목의 source를 `N/A`로 변경하고 테스트에 검증 추가.
- 왜 수용했는가: 데이터 출처가 없다는 상태를 더 정확히 전달하며 응답 스키마는 유지됨.

- 출처: 03_review
- severity: NIT
- 지적 내용 요약: 공급자 호출 예외 흡수 동작에 대한 테스트가 부족함.
- 수정한 파일과 변경 내용: `tests/backend/test_market_service.py`에 Stooq 예외, Frankfurter 예외 케이스를 추가.
- 왜 수용했는가: MAJOR 수정의 핵심 회귀 방지 테스트임.

## 거부한 항목
- 출처: 03_review
- severity: NIT
- 지적 내용 요약: `start-dashboard.bat`의 차단 오류 발생 시 `pause`를 추가해 CMD 창이 바로 닫히지 않게 하는 제안.
- 왜 수용하지 않았는가: 현재 하네스는 non-interactive 실행이며 오류 시 `pause`가 걸리면 자동 검증이나 스크립트 호출이 멈출 수 있음.
- 거부해도 문제가 없는 근거: 배치파일은 이미 오류 메시지를 출력하고 non-zero exit code를 반환하므로 스크립트 계약은 충족함.

## 보류한 항목
- 출처: 03_review
- severity: NIT
- 지적 내용 요약: `02_dev.md`에 KOSDAQ/KOSPI 200 제외 의사결정 사유를 추가하라는 문서 보완 제안.
- 보류 사유: 04_fix 프리셋의 forbidden_writes에 `.ai/features/01-project-init/02_dev.md`가 포함되어 있어 이전 단계 산출물을 수정할 수 없음.
- 별도 처리 제안: 향후 문서 보완 단계가 열리면 Stooq의 KOSDAQ/KOSPI 200 `N/D` 응답으로 KOSPI만 채택했다는 결정을 기록.

## 사용자 판단 요청 항목
- 지적 내용 요약: 없음.
- 선택지 A: 없음.
- 선택지 B: 없음.
- 사용자 결정: 필요 없음.
- 반영 결과: `NEEDS_USER` 없이 기본 정책으로 진행.

## 추가 변경 사항
- 리뷰 반영 과정에서 기존 stale 캐시 보장이 깨지지 않도록, 새 fetch 결과가 전부 unavailable이고 이전 캐시가 있으면 stale 캐시를 반환하는 조건을 추가.
- 왜 추가 수정이 필요했는가: 공급자 예외를 빈 결과로 변환하면 기존 `except` 기반 stale fallback이 작동하지 않으므로 기존 테스트와 사용자 경험을 보존하기 위함.

## 호환성 준수
- 보존한 기존 인터페이스/데이터 포맷/설정 키: FastAPI 라우트, Pydantic 응답 필드, 프론트엔드 타입, 배치파일 경로, 공급자 생성자 인자.
- 호환성 유지 전략 반영 내용: 내부 예외 처리와 기본 timeout만 조정하고 공개 API 구조는 변경하지 않음.
- breaking change 발생 여부: 없음.
- 리뷰/검증 범위를 넘어선 호환성 영향: 없음.

## 변경 파일 목록
- `src/backend/app/services/market_service.py`: 공급자별 예외 격리, 전체 unavailable 시 stale 캐시 fallback 유지, unavailable source를 `N/A`로 변경.
- `src/backend/app/providers/stooq.py`: 기본 timeout을 4초로 조정.
- `src/backend/app/providers/frankfurter.py`: 기본 timeout을 4초로 조정.
- `tests/backend/test_market_service.py`: 공급자 예외 처리 및 `N/A` source 검증 추가.
- `tests/backend/test_stooq_provider.py`: Stooq 기본 timeout 테스트 추가.
- `tests/backend/test_frankfurter_provider.py`: Frankfurter 기본 timeout 테스트 추가.

## 테스트
- 실행한 테스트 명령:
  - `python -m pytest -q tests/backend tests/scripts -p no:cacheprovider`
  - `npm test -- --run` (`src/frontend`)
  - `npm run build` (`src/frontend`)
- 결과:
  - backend/scripts: 15 passed, Starlette `python_multipart` 관련 deprecation warning 1건.
  - frontend tests: 6 passed.
  - frontend build: 성공.
- 추가한 테스트:
  - Stooq 공급자 예외가 발생해도 Frankfurter fallback으로 요약 응답이 계속 생성되는 케이스.
  - Frankfurter 공급자 예외가 발생해도 Stooq 데이터로 요약 응답이 계속 생성되는 케이스.
  - unavailable 항목의 source가 `N/A`로 표시되는 케이스.
  - Stooq/Frankfurter 기본 timeout이 4초인지 검증하는 케이스.

## Git 정보
- fix_base_commit: 94a42d4dd6023cb4869e93973084e2fbb5743a6d
- harness_commit_required: true
- commit_created_by_model: false
- commit_mode_suggestion: create
- commit_message_suggestion: 01-project-init[20260604-215343][04_fix]
- no_code_changes: false
- no_code_changes_reason:
- pre_commit_diff_command: git diff 94a42d4dd6023cb4869e93973084e2fbb5743a6d
- changed_files:
  - .ai/features/01-project-init/04_fix.md
  - .ai/features/01-project-init/04_fix.result.json
  - src/backend/app/providers/frankfurter.py
  - src/backend/app/providers/stooq.py
  - src/backend/app/services/market_service.py
  - tests/backend/test_frankfurter_provider.py
  - tests/backend/test_market_service.py
  - tests/backend/test_stooq_provider.py
- harness_commit_blocking_reason: 없음

## 단계 결과
- status: PASS
- next_stage: 05_verify
- human_gate_required: false
- blocking_reason: 없음
- risk_level: low
- produced_files:
  - .ai/features/01-project-init/04_fix.md
  - .ai/features/01-project-init/04_fix.result.json
- changed_files:
  - .ai/features/01-project-init/04_fix.md
  - .ai/features/01-project-init/04_fix.result.json
  - src/backend/app/providers/frankfurter.py
  - src/backend/app/providers/stooq.py
  - src/backend/app/services/market_service.py
  - tests/backend/test_frankfurter_provider.py
  - tests/backend/test_market_service.py
  - tests/backend/test_stooq_provider.py
- harness_commit_required: true
- commit_created_by_model: false
- commit_mode_suggestion: create
- commit_message_suggestion: 01-project-init[20260604-215343][04_fix]
- test_commands:
  - python -m pytest -q tests/backend tests/scripts -p no:cacheprovider
  - npm test -- --run (src/frontend)
  - npm run build (src/frontend)
- model_mismatch: true
- actual_model: Codex
