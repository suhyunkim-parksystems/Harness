# Project Contract

## Hard Rules
- 모델은 Git commit, amend, reset, checkout, rebase, push를 직접 실행하지 않는다.
- 기존 테스트를 삭제하거나 비활성화하지 않는다.
- 요청 범위를 벗어난 리팩터링, 의존성 추가, 파일 이동은 하지 않는다.
- 기존 코드와의 하위 호환성을 우선한다. 공개 API, 함수 시그니처, 데이터 포맷, 설정 키, 파일 경로, CLI 사용법, 기존 테스트 기대값을 깨뜨리는 변경은 명시적으로 기록하고 사용자 승인을 받는다.

## Project Layout
- 프로덕션 코드는 루트 `src/` 하위에 둔다.
- 테스트 코드는 루트 `tests/` 하위에 둔다.
- 새 테스트 파일을 `src/` 하위에 만들지 않는다.

## Code Style
- 새 코드는 같은 디렉터리의 기존 패턴, 네이밍, 파일 구조를 우선 따른다.
- 프로젝트에 이미 명확한 네이밍 관례가 없으면 변수와 함수는 camelCase를 기본으로 한다.
- 함수 이름은 가능하면 동사 또는 동사구로 시작한다. 예: `loadConfig`, `validateInput`, `renderItem`.
- Boolean 값과 Boolean 반환 함수는 `is`, `has`, `can`, `should` 같은 의미 있는 접두사를 사용한다.
- 이벤트 핸들러는 `handle` 또는 기존 프로젝트의 이벤트 네이밍 패턴을 따른다.
- 값을 변환하는 함수는 `to`, `from`, `parse`, `format`, `normalize`처럼 변환 의도가 드러나는 이름을 사용한다.
- 데이터를 가져오는 함수는 `get`, `load`, `fetch`, `read` 중 실제 동작에 맞는 동사를 사용한다.
- 부수효과가 있는 함수는 `save`, `write`, `update`, `delete`, `send`, `create`처럼 변경 의도가 드러나는 동사를 사용한다.
- 구현이 30줄을 넘어가면 함수나 작은 단위로 분리한다.
- 서비스레이어를 두어서 유지보수를 좋게하라.

## Reliability
- 외부 입력, 파일, 네트워크, 프로세스 실행 결과는 실패 가능성을 명시적으로 처리한다.
