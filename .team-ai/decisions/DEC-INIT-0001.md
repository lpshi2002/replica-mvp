---
id: DEC-INIT-0001
title: Start the standalone Replica MVP
status: active
authority: user-approved
scope:
  - project:replica-mvp
---

## Decision

공개 근거를 테스트 가능한 기능으로 바꾸고, 실행 가능한 AI Replica를 제작·평가해 외부 관찰 범위의 구현 가능성을 보고하는 독립 프로젝트로 시작한다.

## Goal

공개 근거 입력부터 기능 명세, 실행형 Replica, 독립 테스트, 한계가 명시된 리포트까지 한 번에 재현 가능한 최소 흐름을 완성한다

## Constraints

- 기존 팀 아이디어나 회의 맥락을 프로젝트 요구사항으로 가져오지 않는다.
- 원제품 출력에 접근할 수 없으면 동일성 대신 공개 기능의 구현 가능성만 판정한다.
- Do not choose a multi-agent architecture unless decomposition is justified.
