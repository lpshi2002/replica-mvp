---
id: DEC-INIT-0003
title: Adopt the multi-claim two-stage Replica pipeline
status: active
authority: user-approved
scope:
  - project:replica-mvp
---

## Decision

회사 단위 Replica는 기능 하나만 고르는 흐름이 아니라, 1차 공개 조사에서 기업의
주장을 넓게 추출·점수화한 뒤 복제 필요·불필요로 필터링하고, 복제 대상으로 남은
0개 이상의 주장마다 복제에 필요한 공개 자료를 2차로 깊게 수집한 뒤 각각
복제·평가한다.

고정된 회사 단위 흐름은 다음과 같다.

1. 기업명 또는 공개 URL 입력
2. 홈페이지, 서비스 설명, API, 비용, 뉴스 등에서 주장들을 넓게 수집
3. 주장 추출·점수화와 복제 필요·불필요 필터링
4. 남은 주장마다 정확한 범위와 근거를 확인하고, 공개 데이터·샘플·스키마·API·
   구현 단서·평가 자료를 복제 가능한 수준까지 2차 수집한 뒤 1차 결과와 같은
   회사 단위 `research.json`에 결합
5. 실제 Replica 실행을 시작할 때만 준비된 주장 계약을
   `evidence.json`, `spec.json`, `tests.json`으로 펼쳐 주장별 Replica와 Judge 평가
6. 모든 주장에 대해 복제 가능·불가능 여부와 근거를 보고

전체 상위 흐름은 모든 기업에 동일하게 적용하되, 2차 조사 질문과 Replica 구성은
1차에서 발견된 주장에 따라 유동적으로 달라진다.

## Pass boundary

- 1차는 회사 전체를 넓게 훑어 주장 누락을 줄이는 단계다. 중간 상태는 회사 단위
  `research.json`의 출처 목록, 정규화 후보 주장, 라우팅, 3축 점수와 2차 조사
  선택 상태에 기록한다.
- 2차는 선정된 주장 하나에서 시작해 관련 자료만 깊게 확인하고 복제 가능성을
  준비하는 단계다. 같은 URL을 다시 열 수 있지만 회사 전체를 반복 크롤링하지
  않는다.
- 2차가 끝났을 때 조사 산출물은
  `work/<company-slug>/research.json` 하나다. 선택된 각 주장에 `second_pass`를
  붙여 확정 주장, 입력·처리·출력, 기능 경계와 근거, 사용할 데이터·스키마·구현
  단서·평가 자료, 라이선스·접근 한계, 합성 대안과 복제 준비도를 기록한다.
- 2차에서 `confirmed` 또는 `refined`되고 `ready`로 판정되며
  `second_pass.replication_contract`에 미완성 값이 없는 주장만 Replica 단계로
  이동한다. 실행용 파일은 이때 처음 생성한다.

## Transition

현재 단일 기능 `evidence → spec → tests → Replica → Judge → report` 흐름은
실행 단계의 주장별 내부 단위로만 유지한다. 조사 단계에서는 동일 정보를
`research.json`의 주장 항목 안에 보관하고 파일을 미리 펼치지 않는다.

## Constraints

- 주장 수를 하나로 제한하지 않는다.
- 1차에서 구현 데이터, 최종 입출력 계약이나 테스트를 확정하지 않는다.
- 2차에서 공개되지 않은 내용을 추정으로 채우지 않는다.
- 주장 추출 품질은 후속 조사 전체를 좌우하는 현재 위험으로 기록한다.
- 전체 `finance-ai-ideation` pack을 프로젝트 요구사항으로 import하지 않고, 이 결정에 적힌 승인된 내용만 이전한다.
- 조사 패스는 두 번 수행하지만 2차 완료 시점의 회사 조사 결과는 하나만 남긴다.

## Source

- `pack://finance-ai-ideation/sources/meetings/2026.07.23 GH 회의록.pdf#page=2`
- `pack://finance-ai-ideation/sources/meetings/2026.07.23 GH 회의록.pdf#page=3`
- `MEM-AUTH-0063` through `MEM-AUTH-0067`
- User-approved pass boundary in the current Codex task on 2026-07-23.
- User clarification in the current Codex task on 2026-07-24 that pass 2
  collects enough public material to assess and prepare replication.
- User clarification in the current Codex task on 2026-07-24 that pass 1 and
  pass 2 remain separate research passes but produce one combined company
  output.
