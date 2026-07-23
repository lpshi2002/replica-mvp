---
id: DEC-INIT-0004
title: Adopt the Replica public research source policy
status: active
authority: user-approved
scope:
  - project:replica-mvp
---

## Decision

회사 단위 1차 주장 조사와 주장별 2차 복제 자료 조사는 다음 출처 정책을 따른다.

1. 기업 공식 제품·기술 페이지, API·개발자 문서, 도움말, 공개 데모, 기술·
   엔지니어링 블로그, 백서, 릴리스 노트, 공식 GitHub·SDK를 1차 근거로 사용한다.
2. 공식 보도자료, IR·규제 공시, 고객·파트너 공식 발표, 공식 데이터베이스·
   등록부, 연구논문, 특허, Reuters·Bloomberg·FT·WSJ 등 신뢰도 높은 보도를
   보완 근거로 사용한다.
3. 경영진·엔지니어 인터뷰, 컨퍼런스 발표, 공식 채용공고는 기술 단서와 보조
   근거로 사용한다.
4. 투자사 자료, PitchBook, TechCrunch, LinkedIn, Crunchbase는 검색 단서로만
   사용하며, 그 주장만으로 Replica 근거를 확정하지 않는다.

공식 제품·기술 페이지를 열고, 기술·엔지니어링 블로그의 전체 글 목록을 훑은 뒤
각 글의 본문을 직접 확인한다. 제목만으로 관련성을 판단하지 않는다. 회사 자료에서
발견한 시스템·제품·기능 이름은 각각 별도 키워드로 재검색하며, 관련 인터뷰,
컨퍼런스 발표, 공식 채용공고도 확인한다.

회사 단위 `research.json`에서 선택된 주장의 `second_pass`에는 범위,
입력·처리·출력, 경계, 반대 증거와 한계뿐 아니라 실제로 사용할 수 있는 공개
데이터·샘플, 스키마·형식, API·SDK, 구현 단서, 평가 자료, 접근·라이선스 조건과
합성 대안을 기록한다. 그중 복제 설계에 사용할 자료만
`second_pass.replication_contract`에 승격한다. 가능하면 독립 출처를 하나 이상
포함하고, URL과 실제로 확인한 내용만 기록한다.

## Constraints

- 특허는 구현 단서로 사용할 수 있지만 실제 배포된 제품의 증거로 취급하지 않는다.
- 보조·검색 단서의 주장은 공식 1차 자료나 신뢰도 높은 독립 자료로 재검증한다.
- 공개 자료가 부족하면 추정으로 채우지 않고 근거 수준과 한계를 보고한다.

## Source

- User-approved research policy in the current Codex task on 2026-07-23.
