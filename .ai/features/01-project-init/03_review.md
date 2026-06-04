# 03_review - 01-project-init

작성: Antigravity
일시: 2026-06-04

## 리뷰 대상
- 검토한 파일 목록:
  - [src/start-dashboard.bat](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/start-dashboard.bat)
  - [src/stop-dashboard.bat](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/stop-dashboard.bat)
  - [src/backend/app/main.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/main.py)
  - [src/backend/app/config.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/config.py)
  - [src/backend/app/api/routes.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/api/routes.py)
  - [src/backend/app/models/market.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/models/market.py)
  - [src/backend/app/providers/symbols.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/providers/symbols.py)
  - [src/backend/app/providers/stooq.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/providers/stooq.py)
  - [src/backend/app/providers/frankfurter.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/providers/frankfurter.py)
  - [src/backend/app/services/cache.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/services/cache.py)
  - [src/backend/app/services/market_service.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/services/market_service.py)
  - [src/frontend/src/App.tsx](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/App.tsx)
  - [src/frontend/src/hooks/useMarketSummary.ts](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/hooks/useMarketSummary.ts)
  - [src/frontend/src/components/DashboardHeader.tsx](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/components/DashboardHeader.tsx)
  - [src/frontend/src/components/MarketSection.tsx](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/components/MarketSection.tsx)
  - [src/frontend/src/components/MarketTable.tsx](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/components/MarketTable.tsx)
  - [src/frontend/src/components/StatusBadge.tsx](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/frontend/src/components/StatusBadge.tsx)
  - [tests/backend/test_stooq_provider.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/tests/backend/test_stooq_provider.py)
  - [tests/backend/test_frankfurter_provider.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/tests/backend/test_frankfurter_provider.py)
  - [tests/backend/test_market_service.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/tests/backend/test_market_service.py)
  - [tests/backend/test_routes.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/tests/backend/test_routes.py)
  - [tests/scripts/test_batch_files.py](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/tests/scripts/test_batch_files.py)
- base_commit: e8b9a32558dcc9423e1bc036d440d76c7d4c24c4
- review_target_commit: d45eb56a7f02ddc41dd0536e0f8df4c227e964e5
- diff_command: git diff e8b9a32558dcc9423e1bc036d440d76c7d4c24c4..d45eb56a7f02ddc41dd0536e0f8df4c227e964e5
- diff_range: e8b9a32558dcc9423e1bc036d440d76c7d4c24c4..d45eb56a7f02ddc41dd0536e0f8df4c227e964e5

## 지적 사항 요약
- BLOCKER: 0개
- MAJOR: 1개
- MINOR: 2개
- NIT: 2개

## 코드 품질
- severity: MAJOR
- 지적 사항: 외부 API 전체 통신 장애 시 백엔드 대시보드 API 전체 503 에러 발생 및 연쇄 실패
- 해당 코드 위치: [src/backend/app/services/market_service.py#L62-L85](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/services/market_service.py#L62-L85)
- 왜 문제인지: `_fetch_summary`에서 `stooq_provider.fetch_quotes` 및 `frankfurter_provider.fetch_rates`가 각각의 HTTP 네트워크/타임아웃 에러를 발생시킬 때 적절한 try-except 예외 처리가 없습니다. 이로 인해 최초 구동 시점 등 캐시가 빌드되지 않은 시점에 외부 API 중 하나라도 완전히 마비되는 경우(Connection Error 등), 다른 멀쩡한 API(예: Frankfurter) 데이터까지 취합되지 못하고 백엔드가 503 에러를 반환하여 대시보드 화면 전체가 비정상(full failure) 상태가 됩니다.
- 어떻게 개선해야 하는지: 외부 API 요청 호출부를 `try-except`로 감싸서, 통신 장애나 서버 다운 예외가 발생하더라도 이를 로깅하고 빈 결과(`{}`) 등으로 대체해 다른 안전한 지수/환율은 정상 노출하고 에러가 발생한 항목만 개별적으로 `unavailable`로 렌더링되게 해야 합니다.

---

- severity: MINOR
- 지적 사항: 외부 API 호출 타임아웃 기본값의 비효율성 (8초)
- 해당 코드 위치: [src/backend/app/providers/stooq.py#L26](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/providers/stooq.py#L26), [src/backend/app/providers/frankfurter.py#L17](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/providers/frankfurter.py#L17)
- 왜 문제인지: Stooq 및 Frankfurter 공급자 어댑터의 기본 HTTP 타임아웃이 8초로 길게 잡혀 있어, 네트워크 지연 발생 시 사용자가 대시보드 데이터를 조회할 때 최대 8초 이상 로딩이 걸릴 수 있습니다.
- 어떻게 개선해야 하는지: 타임아웃 기본값을 3~5초 정도로 짧게 조정하여 지연 상황 시 빠르게 부분 오류(`unavailable` 상태)를 표시해 사용자 응답성을 높이는 것이 바람직합니다.

---

- severity: MINOR
- 지적 사항: 데이터가 없는 경우의 소스 일괄 표기 오류
- 해당 코드 위치: [src/backend/app/services/market_service.py#L104-L124](file:///D:/WorkingDirectories/vibe-test/Harness_toy/Harness/src/backend/app/services/market_service.py#L104-L124)
- 왜 문제인지: `_to_market_item`에서 `quote`가 `None`인 경우 일괄적으로 `source="Stooq CSV"`를 주입하고 있습니다. 하지만 환율 항목의 경우 Stooq와 Frankfurter fallback 모두에서 실패해 최종 데이터가 없는 것임에도 `Stooq CSV`로 표기되는 것은 정확하지 않은 정보 전달입니다.
- 어떻게 개선해야 하는지: `quote`가 없는 상태일 때는 `source`를 `"N/A"` 등으로 유연하게 지정하거나, 시도한 공급자들의 전체 목록을 기재하는 방식으로 보완이 필요합니다.

## 구조 및 가독성
지적 사항 없음. 외부 공급자 어댑터 및 서비스 캐싱, 라우터 분할이 객체지향적이고 유지보수하기 쉬운 구조로 훌륭하게 설계되어 있습니다.

## 계획 대비 구현 일치성
- severity: NIT
- 01_plan.md 대비 일치/불일치 항목: 한국 지수 기본값 결정 사유
- 구체적 차이: 스펙 문서에서는 한국 지수로 "KOSPI 외에 KOSDAQ 또는 KOSPI 200 추가 표시를 검토한다"고 하였으나, 실제 구현에서는 `symbols.py`에 `KOSPI`만 기본값으로 탑재되었습니다.
- 이 차이가 문제인지, 허용 가능한지: 허용 가능합니다. 실제로 Stooq API를 조회해 본 결과 KOSDAQ(`^kosdaq`) 및 KOSPI 200(`^k200`)의 시세는 무료 quote 엔드포인트에서 지원되지 않아 `N/D`로 응답하므로, KOSPI만 표시하는 것은 정당한 의사결정입니다. 다만 이 사유가 `02_dev.md`에 설명되지 않았으므로 개발 문서에 보완해주면 추후 유지보수 시 유용할 것입니다.

## 호환성 / 회귀 위험
- severity: NIT
- 지적 사항: 필수 도구 미설치 또는 포트 점유 에러 발생 시 배치파일 종료 시인성 저하
- 깨질 수 있는 기존 인터페이스/호출부/테스트: 없음
- 개선 제안: `start-dashboard.bat`에서 포트 충돌이나 파이썬/노드 미설치로 실행이 차단될 때 `exit /b 1`로 바로 종료되어 더블 클릭으로 실행한 사용자는 에러 메시지를 보기도 전에 CMD 창이 닫혀 원인을 알 수 없습니다. 치명적 장애로 진행을 중단할 경우 `pause`를 걸어주면 사용자 경험이 개선될 것입니다.

## 구현 의도 타당성
- severity: NIT
- 02_dev.md에 적힌 판단에 대한 동의 또는 반론: 동의합니다.
- 반론 시 근거: 02_dev.md에서 무료/무인증 Stooq API와 Frankfurter API를 분리 및 조합하고, Windows 환경에서 다른 포트를 충돌로부터 격리하고 PID로 프로세스를 트리 강제 종료하도록 설계한 의도는 타당합니다.

## 테스트
- severity: NIT
- 누락된 테스트 케이스: 실제 외부 API 호출 시의 예외 전파 테스트
- 각 케이스가 왜 필요한지: `StooqProvider` 및 `FrankfurterProvider`의 비동기 fetch 호출 중 발생할 수 있는 httpx HTTPError 예외가 터졌을 때 서비스가 우아하게 처리되는지에 대한 단위 테스트가 부재하여, MAJOR 지적 사항의 예외 삼키기 부재를 사전 방지하지 못했습니다. 추후 04_fix에서 보완이 권장됩니다.

## 04_fix 입력
- must_fix:
  - 외부 API 전체 통신 장애 시 백엔드 대시보드 API 전체 503 에러 발생 해결 (try-except 안전망 추가)
- should_consider:
  - 외부 API 호출 타임아웃 기본값 3~5초 수준으로 하향 조정
  - 데이터가 유실(`unavailable`)되었을 때의 아이템 소스를 `"Stooq CSV"` 고정 대신 `"N/A"`로 개선
- optional:
  - `02_dev.md`에 한국 추가 지수(KOSDAQ, KOSPI 200)가 Stooq `N/D` 문제로 인해 제외된 의사결정 사유 기록 추가
  - `start-dashboard.bat` 차단 에러 발생 시 CMD 창이 바로 닫히지 않고 오류를 볼 수 있게 `pause` 추가

## 총평
전반적인 코드 구조, 분할 설계, Pydantic 직렬화 별칭 대응 및 윈도우 스크립트 프로세스 제어는 수준이 대단히 높습니다.
비동기 병렬 처리(`asyncio.gather`) 및 데드 캐시 폴백(`get_stale`) 역시 스펙 문서의 의도를 세심하게 살려 잘 짜여졌습니다.
다만, 외부 API 통신 장애라는 엣지 케이스 발생 시 연쇄 장애가 일어나 전체 대시보드가 먹통이 될 수 있는 지점이 있으며, 타임아웃 튜닝이나 윈도우 스크립트 시인성 등의 디테일을 조금 더 보강하면 최상의 안정성을 가질 것으로 판단됩니다.

## 단계 결과
- status: PASS
- next_stage: 04_fix
- human_gate_required: false
- blocking_reason: 없음
- risk_level: low
- produced_files:
  - .ai/features/01-project-init/03_review.md
- changed_files:
  - .ai/features/01-project-init/03_review.md
- harness_commit_required: true
- commit_created_by_model: false
- commit_message_suggestion: "docs: 주식 대시보드 프로젝트 초기화 코드 리뷰 결과 작성"
- model_mismatch: false
- actual_model: Antigravity
