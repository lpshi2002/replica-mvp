# AI 테스터 비용 최적화 토론

기준: 2026-10-12, /Users/cho/replica-mvp. 기존 변경이 많은 공유 체크아웃이다.

## 사용자 요청과 권한

출처: 현재 Codex 대화, 2026-10-12.
- 사용자: "그럴거면 그냥 싼모델 시키지뭐 그래서 해야되는 최적화 내용이 뭐라고"
- 사용자: "이게 테스트가 구현을 하면서 진행하는거야 아니면 다 구현하고 테스트하고 수정하고 테스트하고 이걸 말하는거야"
- 사용자: "그러면 방금 말한 최적화에 대한 부분을 클로드랑 토론한번 해봐"
- 중단 후 사용자: "계속 진행해봐"

이번 권한은 최적화 설계의 토론과 읽기 전용 근거 확인, 토론 문서 작성이다. 제품 코드·복제품·시험 계약·프로젝트 방향을 수정하거나 커밋·배포하거나 유료 브라우저 평가를 실행하지 않는다. Jev 등 새 공급자 도입은 이번 권고의 우선순위에서 제외한다. 모델·추론 설정을 임의로 바꾸지 않는다.

## 보존할 확정 요구

- 기업 입력 이후 사람의 중간 개입 없이 조사·구현·평가를 수행한다.
- AI는 사람이 체험하는 실제 웹 앱의 화면에서 입력·클릭·업로드·대화를 하고 실제 결과를 확인한다. 내부 API/파일 검사만으로 이 경로를 대체하지 않는다.
- 의미·답변 품질·근거 충실도 등은 별도 모델 판정을 유지한다. 내부 `sent` 기록을 외부 발송 성공으로 인정하거나, 기대 결과·시나리오를 약화하지 않는다.
- 기능별 구현자는 작성→개발 검사→수정을 반복한다. 실행 가능한 앱에서 개발 AI 시연도 가능하고, 제출 버전은 구현자와 분리된 최종 평가를 받는다.
- 이미 실행된 결과·동결 사례·사용 값·원본 증거를 보존한다. 버전이 다른 앱의 과거 통과를 새 버전의 통과로 이전하지 않는다.

## 이번에 검토할 기존 제안

O1. 한 화면의 짧은 행동을 한 모델 응답에 묶는다. 각 행동의 관측·기록은 유지하고 예상 밖 화면이면 중단한다.
O2. 입력 반영·체크 상태·버튼 활성화·로딩 완료 같은 기계적인 확인·대기를 코드로 수행한다.
O3. 테스터 입력을 현재 단계·필요한 화면 정보·최근 오류 중심으로 줄인다. 전체 증거는 보관하고 필요 시 추가 읽기 한다.
O4. 단순 상태·저장·개수·중복은 결정적 검사, 의미·정확성은 LLM 판정으로 나눈다. 필요한 증거만 Judge에 보낸다.
O5. 개발 중에는 관련 사례부터 재시험하고 최종 제출 버전은 전체 계약 범위를 검증한다.

이 다섯 가지는 진행자의 제안이며 사용자가 구현을 승인한 상태가 아니다. 실행 가능한 최소 변경, 잘못된 통과 위험, 기대 이득을 코드와 기록으로 반박·수정해 달라.

## 이미 적용된 것과 비용 분모

현재 미커밋 코드에 역할별 모델 선택, Sonnet 테스터 실행, `wait_for`, 긴 값 읽기·check/uncheck, 중간 관측, 사례 선택, 체크포인트, 한도 차단, 같은 번들의 평가 복구, 누적 비용 집계가 있다. 이 항목들을 새 개선으로 세지 않는다. 회사 앱 조립도 미커밋 상태다.

- 평가+등록 개발 시연 전체 누적: 1,430호출 / $44.285092. 그중 tester 1,111호출 / $31.142093. 실제 청구액이 아니라 CLI 기록 정가 추정이다.
- 최종 채택된 세 평가 실행의 합: 전체 $13.702076, tester 401호출 / $8.208604. 모든 최적화가 동일하게 적용된 새 회사 전체 실행 비용은 아니다.
- 동일 Actions 앱 candidate 31975ba1bb37 및 동일 plan: tester Opus198호출/$6.801201 → Sonnet185호출/$3.404307. 전체 평가 $8.798612 → $5.570822. 양쪽 7사례 모두 처음부터 시작, 각6완료. 이후는 생성 입력만 재사용, `lineage.reused_evidence=false`.
- 따라서 전체 누적 $31.14가 $3.40으로 줄었다고 할 수 없다. 같은 회사의 전체 제작 경로를 같은 조건으로 비교한 절감률은 미측정이다. 모델·관측·대기가 함께 바뀌어 효과 분리가 안 된다.

## 필요한 근거 위치

우선 `/Users/cho/replica-mvp/context/project-direction.md` 5절과 `/Users/cho/replica-mvp/skills/replica-research/SKILL.md` Freeze/Execute 절을 읽는다. 오래된 현황표보다 현재 코드/실행 기록을 우선해 구현 여부를 확인한다.

- `/Users/cho/replica-mvp/src/replica_mvp/web_demo.py`: TESTER_SCHEMA, _OBSERVE_SCRIPT, _tester_prompt, _perform, _wait_on_screen, _run_case, _evaluate_case, _screen_evidence.
- `/Users/cho/replica-mvp/src/replica_mvp/web_evaluation.py`, `web_checkpoint.py`, `model_calls.py`.
- `/Users/cho/replica-mvp/docs/replica-implementation-guide.md`: 이미 있는 선택 개발 시험·역할 모델·문맥 정책.
- `/Users/cho/replica-mvp/tests/test_web_demo.py`, `tests/test_web_evaluation.py`, `tests/test_pipeline_efficiency.py`.
- 요약/계산: `/Users/cho/replica-mvp/tmp/reviews/delphi-v4-postrun-review-2026-10-12.md`, `delphi-v4-postrun-metrics-2026-10-12.json`, `delphi-v4-postrun-probes-2026-10-12.json`.
- 원본: `/Users/cho/replica-mvp/work/delphi-ai-v4/single-harness-2026-10-09/final-results/company-claims.json`.
- Actions 비교: 같은 root의 `final-results/runs/claim-002/web-attempt-001-31975ba1bb37` 및 `web-attempt-002-31975ba1bb37`: `demo-result.json`, `events.jsonl`.

요약 보고서는 검토자의 주장이므로 필요한 코드/원본과 대조한다. 원본 로그 전체를 무차별로 읽거나 유료 실험을 실행할 필요는 없다.

## 완료 기준

각 O1~O5에 채택·축소·보류·기각과 이유를 정한다. 현재 구현과의 차이, 구체적인 작업 단위, 증거·중단·예산 처리, 개발 대 최종 평가 경계, 최소 검증 방법, 적용 순서를 합의 또는 이견으로 남긴다. 중요한 반론은 수정안까지 다시 검토한다. 모델 간 동의와 실측 효과·사용자 승인을 구분한다.
