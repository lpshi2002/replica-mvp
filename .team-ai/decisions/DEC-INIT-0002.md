---
id: DEC-INIT-0002
title: Use the current Codex task as the Replica orchestrator
status: active
authority: user-approved
scope:
  - project:replica-mvp
---

## Decision

사용자는 현재 Codex 대화에 기업명이나 공개 URL만 입력한다. 현재 Codex
태스크가 공개 조사, 기능 선정, 사양과 테스트 작성, Replica 실행, Judge
판정, 보고서 생성을 오케스트레이션한다.

## Constraints

- 제품 코드가 Codex CLI나 모델 API를 다시 호출하지 않는다.
- 사용자가 JSON, 프롬프트, 테스트, 모델 명령을 직접 작성하지 않는다.
- 공개 근거가 없는 사실은 생성하지 않으며 원제품 출력이 없으면 동일성을
  주장하지 않는다.
- Replica 생성과 Judge 판정은 가능한 범위에서 서로 분리하고, 동일 세션
  판정이면 그 한계를 보고서에 밝힌다.
