---
id: DEC-INIT-0005
title: Score Replica claims on moat, business, and separability
status: active
authority: user-approved
scope:
  - project:replica-mvp
---

## Decision

사람이 확정한 각 주장 후보를 다음 세 축에서 0~2점으로 채점한다.

1. `moat`: 단순 기능 0 / 일부 차별점 1 / 반복 강조 핵심 해자 2
2. `business`: 부가 기능 0 / 고객 편의 1 / 구매·유지 핵심 2
3. `separability`: 영업·브랜드·계약 0 / 기술·사업 혼합 1 /
   제한된 입력→출력 기술 2

`total`은 세 점수의 합인 0~6점이다. 외부에서 신뢰할 만한 데이터를 얻기 어려운
`observability`와 `judgeability`는 수집·채점·선정 기준에서 제외한다.

확정되고 복제 가능한 주장 중 `total >= 4`인 주장을 전부 2차 심층 조사 대상으로
선택한다. `total <= 3`은 선택하지 않는다. 복제 불가능한 주장은 총점이 4점 이상이어도
Replica로 보내지 않고 소명 요구로 전환한다.

각 후보에는 원 주장, 근거, 테스트 가능한 재서술, 라우팅, 복제 가능 여부, 세 축의
점수와 근거, 합계, 선택 상태와 이유를 기록한다. 복제 불가능한 주장은 Replica로
보내지 않고 소명 요구로 전환한다.

## Constraints

- 모델은 주장 재서술과 라우팅을 제안만 하며, 사람의 `confirmed | edited |
  rejected` 확정 전에는 채점하지 않는다.
- 너무 넓은 주장은 독립적으로 테스트 가능한 단위로 분리한 뒤 다시 판정한다.
- 공개 자료가 부족한 주장을 추정으로 보완하지 않는다.
- 접근성이나 오라클 한계는 필요하면 제한사항으로 서술하되 점수에는 넣지 않는다.

## Source

- `/Users/cho/Downloads/10-replica-step1-collection.md`
- User correction in the current Codex task on 2026-07-23 removing
  `observability` and `judgeability`.
- User decision in the current Codex task on 2026-07-23 setting the
  three-axis selection threshold to `total >= 4`.
