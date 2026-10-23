# classification-boundary-rules

작업 ID: 5570f720-5829-4beb-909e-71d4516429ab

## 현재 상태
종료(resolved). 제안 [001](001-claude-proposal.md), 검토 [002](002-codex-review.md). 진행자(Claude)가 Codex 근거를 확인하고 전 쟁점 수용.

## 현재 판단
원칙(1~4번)은 범용적으로 유지. 현재 diff 그대로 확정은 보류, 아래 보완 후 확정.

| ID | 판단 | 핵심 이유 |
|---|---|---|
| I1 | 기각(경미 보완) | worker 문장은 "only when" 필요조건이라 새 3번과 양립. 경계 절 링크만 추가 |
| I2 | 수용 | `not_workflow` 정의를 "관계 미확정 지원 단계"까지 확장. `no_ai_attribution`은 독립 AI claim 탈락 사유로 유지. enum 추가 불필요 |
| I3 | 범위 축소 수용 | coverage 검증은 이미 존재(project.py:692, second_pass.py:524 등). 없는 것은 claim 간 관계 대조 절차와 overlap의 최종 결과 전달 |
| I4 | 기각(보완 1건) | 2차 merge 조건은 공유 기능과 양립. 공유 기능의 새 근거 발견 시 관련 worker 재개 책임만 추가 |
| I5 | 기각 | 예시는 원칙 설명용. 작성·실행을 각각 C0~A2로 판단한다고 명확화 |
| I6 | 보류 | 범위 포함 ≠ 코드 재작성. 비용 미측정, 병목 확인 시 재검토 |
| I7 | 신규·수용 | 3번(목적·완료 결과)과 SKILL.md:324(+시작 입력·AI workflow) 동일성 기준 불일치. 시작 조건·책임·상태·완료 조건 대조로 통일 |
| I8 | 신규·수용 | "관계 있음"과 "해당 claim의 필수 단계"를 구별. 조건부 단계는 조건과 함께 보존 |
| I9 | 신규·수용 | excluded에는 ID·excerpt 없음(project.py:540), 집계는 길이 합(project.py:833). 재분류 시 이력 보존·집계 구분 절차 필요 |

## 다음 행동
2026-10-22 사용자 승인으로 반영 완료(문서만, 커밋 전). 상세는 [conclusion.md](conclusion.md) "사용자 결정과 반영". 다음 기업 평가는 새 작업 폴더에서 1차부터 실행.
