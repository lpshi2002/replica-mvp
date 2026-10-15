# 남은 AI 테스터 비용 최적화 후속 토론

2026-10-12. 기존 tester-cost-optimization-1be6cda7의 후속이다. 이전 작업은 스크립트에서 closed이며 재개 명령이 없어 새 후속 작업으로 연결한다. 기존 결론과 의견은 보존한다.

## 사용자 요청과 맥락
- 사용자는 O3 구현 뒤 “그렇게 많이 줄어보이지는 않는데 결국 브라우저 쓰는 애는 계속 남아있는거 아님?”이라고 지적했다.
- 진행자가 매 행동 모델 호출이 그대로이며 단순 조작을 코드 실행으로 넘기는 행동 묶음이 다음 핵심이라고 설명하자, 사용자는 “나머지도 토론진행해봐”라고 요청했다.
- 이 요청은 남은 최적화의 토론이다. 제품·복제품·동결 사례 수정이나 회사 전체 유료 평가 실행은 이번 범위가 아니다.

## 확인된 현재 상태
- O3는 이미 구현됨. 최근 15개/실제 입력/오류/현재 화면/원본 증거/Judge 유지, 성공 이유160자·null·JSON 공백 축소.
- 저장 401개 행동 이력 바이트15.63%, 관측이 있는323개 전체 프롬프트 바이트8.07% 감소. 토큰·요금 절감이나 라이브 행동 품질은 미측정. 전체370테스트 통과는 직전 구현 검증이며 이번 토론에서 다시 실행한 것이 아님.
- 브라우저 화면을 통한 실제 입력과 결과 관측, 성능·의미 평가의 독립 LLM Judge, 기업 입력 이후 무인 실행은 유지해야 함. 클릭 성공/내부 기록만으로 실제 외부 효과를 충족 처리하면 안 됨.
- 새로운 모델 공급자·Jev 도입은 범위 아님. 역할별 저렴한 모델 지정·wait_for/check/uncheck·선택 사례 시험·체크포인트는 이미 있음.

## 이번 쟁점
- O1: 한 번 판단하고 여러 단순 동작을 코드로 수행하는 최소 설계. 폼 입력+마지막 버튼과 더 넓은 절차 계획/재실행을 비교. 어디에서 LLM이 다시 보고 판단해야 하는가? 분기·변경된 DOM·중복 제출·관측 누락·비용 상한을 어떻게 다룰까? 효과 대비 복잡성이 타당한가?
- O6: 현재 CLI의 고정 지침 재사용/캐시가 실제 절감 가능한가? 현재 영수증과 CLI 경계를 확인해 무용한 프롬프트 이동을 걸러낼 것. 고정 지침만 분리 후보, 사례/facts/앱 화면을 시스템 권한으로 올리지 않을 것.
- O2/O4/O5: 이미 있는 자동대기·결정적 검사·선택 시험 중 운영/코드상 더 적용할 것이 있는가? 단순 검사 도입이 Judge 호출을 실제 없애는 경우와 그대로인 경우를 구별. 전체 DSL/영향분석 엔진을 근거 없이 도입하지 않을 것.
- O7: 다음 구현 우선순위와 최소 검증, 중단·채택 조건. 범위를 줄여 싸게 보이는 것과 동일 범위 비용 감소를 구별. 모델 간 합의를 실측으로 표현하지 않을 것.

## 참조 (필요 범위만 읽기)
- 이전 결론: context/tasks/tester-cost-optimization-1be6cda7/conclusion.md 및 004-claude-review.md
- 이번 O3: docs/tester-history-optimization-2026-10-12.md
- 코드: src/replica_mvp/web_demo.py(_OBSERVE_SCRIPT,_tester_prompt,_perform,_wait_on_screen,_run_case,_evaluate_case), model_calls.py(run_model_cli), web_checkpoint.py
- 검증: tests/test_tester_history.py, tests/test_pipeline_efficiency.py, tests/test_web_evaluation.py
- 비용/행동 근거: context/tasks/tester-cost-optimization-1be6cda7/coordinator-verification.md, coordinator-adjacency-evidence.json, coordinator-terminal-click-evidence.json
- 저장 실행: work/delphi-ai-v4/single-harness-2026-10-09/final-results/runs/{claim-001/web-attempt-004-5fa1c5939ec3,claim-002/web-attempt-002-31975ba1bb37,claim-003/web-attempt-002-a80003d5034d}

## 완료 기준
실제 코드를 읽은 제안→반론→수정안 재검토로 중요한 설계 쟁점을 해결한다. 정량 근거는 분모와 한계를 표시한다. 남은 검증이 무엇인지, 무엇부터 구현해야 하는지 구현 가능한 수준으로 정리한다. 기존 작업은 보존하고 유료 A/B 효과를 추정치로 단정하지 않는다. 간결한 한국어 보고서, 원자료 대량 복사는 피한다.
