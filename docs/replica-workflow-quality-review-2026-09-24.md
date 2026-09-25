# Replica 전체 워크플로우 품질 검토

검토일: 2026-09-24, Asia/Seoul. 기준: `codex/sol-terra-implementation-bundle`의
`fa44d73`. UI는 제외한다. 2026-09-25에 발견 사항을 수정했고, 결과는
[7. 조치 결과](#7-조치-결과-2026-09-25)에 있다. 아래 1~6절의 줄 번호는 수정 전 `fa44d73` 기준이다.

## 결론

구현·평가·배포 쪽에는 해시 결속, 봉인 평가, 제출 제한 같은 장치가 갖춰져 있다.
반면 **그 앞단에서 고객 작업이 빠지거나 줄어드는 것을 막는 장치가 약하다.** 문제는
두 층위다.

1. **2차에 도달하기 전.** 1차에서 수집한 후보가 설명 없이 사라지거나, 배정된 조사를
   하지 않았는데 완료로 처리될 수 있다.
2. **2차 계약.** 2차가 고객 작업을 작은 처리 함수로 줄여도, 계약 형식만 맞으면
   구현이 시작된다. 그러면 이후 구현을 정교하게 만들어도 줄어든 기능의 산출물만
   남는다.

Delphi 인터뷰가 그 사례다. 조사한 워크플로우에는 질문 제시와 후속 진행이 있지만,
1차의 테스트 가능한 재서술부터 이미 "답변 한 건 → 주제·요약"으로 좁아졌고, 2차가
이를 명시적으로 동결했다. 최신 구현에는 실제 모델 생성·검색·Dagu 실행·SQLite
저장이 있으므로 고정 응답 데모로 볼 수는 없다. 다만 그것과 전체 고객 워크플로우의
재현은 별개다.

2차가 조사하고 범위·방법을 정하는 책임은 유지한다. 대신 **방법을 단순화한 것과 고객
기능을 삭제한 것이 구분되어 기록되고, 구현 전에 검증되어야 한다.** 2차 프롬프트만
고쳐서는 부족하다. 1차 완료 검증, 2차 계약 스키마, 시작 전 검증을 코드로 보완해야
한다.

## 검증 범위와 해석

- 조사 Skill과 1·2차 worker 계약, 연구 입력과 보완본, 계약 파서, 하네스·인계,
  Agent 실행·평가·배포·체험 경로, 테스트와 완료 기준을 검토했다.
- 기준 커밋에서 자동 테스트 262개가 통과했고 GitHub CI(Tests, Security tests)도
  통과했다. 테스트 통과와 아래의 조사·계약·평가상 빈틈은 동시에 성립한다.
- **재현**은 임시 디렉터리에서 실제 함수를 호출해 확인한 것이다. **코드 확인**은
  경로를 읽어 확인한 것이다. **설계 공백**은 실제 실패 사례까지 입증하지 않은
  책임·지침의 공백이다.
- 9월 8일 최종 평가와 9월 23일 직접 실행 결과는 보존된 기록을 검토한 것이다. 새
  Agent 실행이나 실제 모델 호출은 하지 않았다. 모델 품질이나 원서비스 동작을 다시
  측정한 결과로 해석하면 안 된다.
- 실행 증거는 `work/`(Git 제외, 로컬 전용)에 있다. 아래에서 `work/...` 경로는
  링크가 아니라 로컬 위치다.

## 이번 검토 과정에서 해결한 항목

| 항목 | 조치 | 커밋 |
|---|---|---|
| 1차 조사 규칙 회귀 | `dccdf79`가 7/25 사본으로 Skill·템플릿을 재구성해, 점수화(`moat+business+separability ≥ 4`)가 부활하고 1·2차 worker 계약과 `finalize-pass-1` 검증이 삭제돼 있었다. `8422e1e`의 규칙을 복원하고, 이후 추가된 experience·번들·하네스·구현 경로 규칙은 보존했다. 폐기된 `scores/total/selected/disposition`은 이제 검증에서 거부된다. | `fa44d73` |
| 미커밋 평가 파이프라인 | 봉인 평가·공개 산출물·예산·복구 장치와 관련 Skill·문서가 로컬에만 있었다. 커밋하고 푸시했다. Delphi 9/8 결과는 이 코드로 실행됐다. | `861e8ba`, `b6612ca`, `17345d6` |
| macOS 테스트 실패 | Python 부품의 메모리 제한이 macOS에서 매번 실패했다. | `fa1b4d1` |

## 1. Delphi의 조사된 작업과 현재 계약 비교

원기능 범위는 저장소가 수집한 공개 설명을 기준으로 한다. 원제품의 비공개 구조·품질·
진행률 계산식과의 동일성을 요구하지 않는다.

| 기능 | 조사된 고객 작업 | 현재 실행 가능한 범위 | 전체 작업을 목표로 할 때 부족한 부분 |
|---|---|---|---|
| 자료 기반 대화 | 창작자 지식·설정 준비, 질문·대화 맥락 해석, 지식에 근거한 응답 | 호출자가 corpus·규칙·대화 이력을 주면 실제 검색·모델 응답 | 지식의 등록·갱신·식별과 대화 이력 관리가 호출자 책임으로 남음 |
| 상황별 Actions | 작업 설정, 이벤트·대화 맥락 판단, 승인 정책, 후속 작업과 계속되는 대화 | 자연어 지시·이벤트를 받아 모델이 판단하고 Dagu로 로컬 작업 기록 생성 | 정상적인 되묻기 응답의 노출, 호출 간 승인·예약·중복 억제 상태 |
| 창작자 인터뷰 | 주제·질문 제시, 답변에 따른 후속 진행, 인사이트·지식 저장 | 호출자가 현재 주제·질문·답변을 주면 후속 주제·요약을 생성하고 SQLite 저장 | 최초 질문 생성, 실제 다음 질문, 세션 진행·재개, 저장한 지식을 대화에 쓰는 연결 |

기능별로 독립 구현한 것 자체는 문제가 아니다. 문제는 부분 구현을 전체 고객 작업의
완료로 올려 잡는 것이다. UI·음성·영상을 제외하는 것과 질문 생성·대화 상태·지식
연결을 제외하는 것은 서로 다른 범위 결정이다. 후자는 로컬 JSON/CLI만으로 구현할
수 있고, 제외한다면 부분 재현으로 명시해야 한다.

근거(로컬): `work/delphi-ai/research.json`의 인터뷰 `workflow.steps`와
`testable_claim`, 2차 readiness의 "narrows the reproduction to one
answer-to-follow-up-topic-and-insight transaction",
`work/delphi-ai/manual-check-2026-09-23-235652/report.md`.

## 2. 발견 사항

P0은 다음 전체 워크플로우 구현 실험 전에 반드시 해결할 항목, P1은 그 실험의 결과를
신뢰하기 위해 필요한 항목, P2는 사용성·유지보수 항목이다.

### ① 1차 완료 검증

#### A1 · P0 · 수집한 후보가 2차로 가기 전에 설명 없이 사라질 수 있다 — 재현

`finalize_first_pass`는 보류(`deferred`) 항목의 처리 결과만 대조한다. 체크포인트의
일반 후보가 최종 claim이 됐는지, 다른 claim에 병합됐는지, 근거를 두고 제외됐는지는
대조하지 않는다.

- **재현.** 체크포인트 후보 5개, 최종 `claims=[]`인 입력이 `pass_1_complete`로
  승인되고 `next_step=no_ai_claims`가 기록됐다.
- **영향.** "1차에서 수집한 기능을 모두 2차에서 검증한다"는 흐름이 보장되지 않는다.
- **권고.** 후보별 최종 처리(`claim`, `merged_into`, `excluded`)와 연결 대상·사유를
  요구하고, 모든 체크포인트 후보가 정확히 하나의 처리를 갖는지 검증한다. 개수
  비교만으로는 부족하다.

근거: [project.py:700-782](../src/replica_mvp/project.py#L700)

#### A2 · P0 · 배정된 조사 범위를 실제로 완료했는지 확인하지 않는다 — 재현

`assignment.assigned`와 `progress.completed`가 각각 리스트인지만 확인하고, 두 목록의
대응은 확인하지 않는다.

- **재현.** 배정 2개, 완료 0개, `remaining=[]`, `status=complete`인 체크포인트가
  승인됐다.
- **권고.** 배정 항목마다 완료 근거나 미수행 사유를 요구한다. 조사가 충분했는지라는
  질적 판단 이전에, 배정된 조사를 수행했는지부터 검증해야 한다.

근거: [project.py:576-584](../src/replica_mvp/project.py#L576)

#### A3 · P1 · 1차 완료 명령을 다시 실행하면 상태가 후퇴한다 — 재현

기존 진행 상태와 관계없이 `workflow.status`를 `pass_1_complete`로 덮어쓴다.
`pass_2_complete` 입력이 `pass_1_complete`로 바뀌었다. 2차 데이터 자체는 유지된다.
완료된 조사에서는 이 명령을 거부하거나 새 버전으로만 처리해야 한다.

근거: [project.py:760](../src/replica_mvp/project.py#L760)

### ② 2차 계약과 구현 시작 전 검증

#### B1 · P0 · 고객 작업을 줄인 계약을 그대로 동결할 수 있다 — 설계 공백, Delphi 사례

인터뷰의 원래 단계에는 시스템의 질문 제시가 있다. 그런데 1차 `testable_claim`이
이미 "답변 → 후속 주제·요약"으로 줄었다. 2차는 `current_topic`, `active_question`,
`answer`를 입력으로 요구하고, 출력에 실제 다음 질문이 없는 계약을 동결했다.

2차 worker 지침은 "오픈소스 전용 경로는 더 좁은 조건을 가진다"고 서술해 좁은
계약을 정당화한다. 워크플로우 단계를 계약에 대응시키는 장치도 없다. 최소 테스트
3개(정상·경계·정보부족)는 상한이 아니라 최솟값이므로, 그 자체가 축소의 원인은
아니다.

- **권고.** 1차에 원래 고객 목적·시작·종료 조건과 필수 단계 식별자를 보존한다.
  2차가 각 단계를 `구현`, `명시적 외부 의존`, `제외(사유·상위 작업 영향)`, `미확인`
  중 하나로 연결하게 하고, 파서가 이 대응표를 검증한다. 공개 자료로 확인한 필수
  단계를 제외하면 상위 고객 작업의 부분 범위로 표시한다.
- **완료 확인.** 현재 인터뷰 입력을 넣으면 최초 질문·후속 질문·진행/재개 단계의
  누락이 구현 전에 검출되어야 한다.

근거: [replica-second-pass.md:171](../skills/replica-research/agents/replica-second-pass.md#L171)

#### B2 · P0 · 2차 worker 계약이 번들 실행에 필요한 필드를 모른다 — 지침 확인

시나리오 선택(`selected_scenario_id`, `scenario_priority`), `evaluation`,
`experiment_budget`, `experience`는 SKILL에만 있고, 실제로 `second_pass`를 쓰는 worker
계약에는 없다. orchestrator는 2차에서 직접 조사하지 않는다.

정상 절차를 따르면 이 데이터가 비고, 결국 구현 단계에서 스크립트로 채우게 된다.
Delphi 9/8 보완본은 `prepare_research.py`로 이 필드를 채웠다(B3 참고).

- **권고.** worker 계약과 출력 템플릿에 해당 필드와 작성 기준을 넣는다. 번들 경로의
  평가 데이터는 2차 산출물로 만든다.

근거: [SKILL.md:416-496](../skills/replica-research/SKILL.md#L416),
[replica-second-pass.md](../skills/replica-research/agents/replica-second-pass.md)

#### B3 · P0 · 2차 판정을 새 근거 없이 뒤집을 수 있다 — Delphi 사례

Delphi Actions의 원래 2차 판정은 `partial`/`evidence_request`였다. 사유는 "공개되지
않은 compiler 동작의 기대값을 동결하면 재현이 아니라 동작을 지어내는 것"이었다.
9/8 보완 스크립트의 `select()`가 세 claim의 readiness를 모두 `ready`로 덮어썼다.
새로 추가한 근거는 `excerpt: ""`와 일반적인 `type`이었다. 파서는 이를 그대로
수락했다. 보완본 상단과 하단의 집계는 ready 2개/partial 1개로 남았다.

- **권고.** readiness·handoff를 바꿀 때는 이전 판정, 번복 사유, 비어 있지 않은 새
  근거를 요구하고 파서에서 검증한다. 원판정은 보존하고 새 버전으로 기록한다.

근거(로컬): `work/delphi-ai/implementation-check-2026-09-08/prepare_research.py`의
`src()`, `select()`, 같은 디렉터리 `research.json`의 `preparation`과 `workflow.pass_2`.

#### B4 · P1 · 자료를 찾은 것을 실행 경로가 있는 것과 같게 본다 — 지침 결함

worker 지침은 "`oss_papers_patents`가 채워지면 `oss_only` 경로가 있고,
`datasets_apis`가 채워지면 `commercial_api` 경로가 있다"고 서술한다. 논문·특허를
찾았다고 사용 가능한 구현이 있는 것은 아니고, 데이터셋을 찾았다고 상용 API 경로가
있는 것도 아니다. 자료 발견과 실행 경로 확인을 분리해야 한다. 이 문구 때문에 특정
실행이 실패했다는 인과는 입증하지 않았다.

근거: [replica-second-pass.md:181-183](../skills/replica-research/agents/replica-second-pass.md#L181)

#### B5 · P1 · 병합 판정한 기능을 상위 기능에 반영할 책임이 불명확하다 — 설계 공백

worker는 다른 claim을 읽을 수 없어서 부모를 지정하지 않고 `merged`와
`replication_contract=null`을 반환한다. orchestrator는 병합 결과를 수집·보고하라는
지시만 받는다. 조사한 단계와 근거를 부모로 옮기고 부모 계약을 다시 검증하라는 완료
조건이 없다. 실제 유실 사례는 재현하지 않았다.

근거: [replica-second-pass.md:114](../skills/replica-research/agents/replica-second-pass.md#L114),
[SKILL.md:353](../skills/replica-research/SKILL.md#L353)

#### B6 · P1 · 준비가 부족해도 구현을 시작한다 — 코드 확인

파서는 `confirmed/refined`, `ready`, `build`, 시나리오 기본 형식만 확인한다. 조사
완료 상태, 1차 검증 통과, 선택 시나리오의 테스트 존재, 워크플로우 대응은 확인하지
않는다. 평가 준비기는 빠진 실행 방식·평가 범위·새 입력 등을 `gaps`에 기록하지만
실행을 막지 않는다.

최종 판정이 `gaps`를 실패 조건에 반영하므로 **시작 허용이 곧 거짓 성공은 아니다.**
문제는 구현 비용을 쓴 뒤에야 막힌다는 점이다.

- **권고.** 필수 gap이 있으면 Agent 활성화 전에 `RESEARCH_INCOMPLETE` 같은 상태로
  돌려보낸다. 필수 기능을 막는 미확인과 허용되는 비공개 세부사항을 구분한다.

근거: [second_pass.py:266-299](../src/replica_mvp/second_pass.py#L266),
[bundle_evaluation.py:241-262](../src/replica_mvp/bundle_evaluation.py#L241)

#### B7 · P2 · 실행 순서 설명이 서로 다르다 — 문서 모순

하네스가 선택한 시나리오 하나만 실행하고 다음으로 넘어가지 않는 것은 SKILL 실행
절에 명시된 정책이다. 하지만 계약을 쓰는 쪽 지침은 여전히 "첫 시나리오를 실행하고
재현되면 멈춘다"는 전제를 둔다. 코드 결함은 아니다.

근거: [replica-second-pass.md:186](../skills/replica-research/agents/replica-second-pass.md#L186),
[SKILL.md:400](../skills/replica-research/SKILL.md#L400),
[SKILL.md:482-491](../skills/replica-research/SKILL.md#L482)

### ③ 평가와 판정

#### C1 · P1 · 통과 사례가 없어도 `partially_reproduced`가 된다 — 재현

출력이 하나라도 있으면 통과 수와 관계없이 `partially_reproduced`다. 0/6 통과로
재현했다. Delphi 세 기능의 "부분 재현"도 통과 수와 연결된 라벨이 아니다. 핵심 기준
통과를 기준으로 정의하거나, "출력은 있으나 미재현"을 별도 상태로 분리한다.

근거: [completion.py:488](../src/replica_mvp/completion.py#L488)

#### C2 · P1 · 사례 하나의 시간 초과를 전체 예산 소진으로 처리한다 — 코드 확인

사례별 제한 시간 초과도 `stop="budget_exhausted"`가 되어 이후 사례를 모두 건너뛴다.
구현 결함일 수 있는 상황이 `execution_blocked`로 분류될 수 있다. 개별 사례 시간
초과와 전체 예산 소진을 구분해야 한다.

근거: [bundle_evaluation.py:380-392](../src/replica_mvp/bundle_evaluation.py#L380)

#### C3 · P1 · 평가 사례가 격리되지 않고, 상태 연결도 선언되지 않는다 — 코드 확인

모든 사례를 하나의 서버·작업 디렉터리에서 순서대로 실행한다. Delphi Actions의
`duplicate-event`는 앞선 `normal` 사례가 남긴 상태를 암묵적으로 전제한다. 앞 사례가
실패하면 연쇄 실패하고, 순서를 바꾸면 결과가 바뀐다. 사례는 기본적으로 격리하고,
상태가 필요한 흐름은 단계 목록을 가진 sequence 사례로 명시한다.

근거: [bundle_evaluation.py:403](../src/replica_mvp/bundle_evaluation.py#L403)

#### C4 · P1 · 파일이 없어야 정상인 응답을 산출물 수집기가 실패로 바꾼다 — 코드 확인, 기록

`output_artifacts`는 경로와 미디어 타입만 선언할 수 있다. 모든 결과에서 무조건 실제
파일을 요구하므로 `needs_clarification`, `not_triggered`, `awaiting_confirmation`처럼
효과가 없어야 하는 응답이 실패한다. 9/23 Actions 직접 실행에서는 내부 서버가 정상적인
`needs_clarification`을 반환했는데 CLI가 파일 오류로 실패했다.

결과 상태별 산출물 존재 조건을 2차에서 동결한다. 가짜 파일을 만들거나 경로·해시
검증을 제거하는 방식으로 해결하지 않는다.

근거: [bundle_evaluation.py:222-228](../src/replica_mvp/bundle_evaluation.py#L222),
[bundle_evaluation.py:329-340](../src/replica_mvp/bundle_evaluation.py#L329)

#### C5 · P2 · "결과가 달라져야 한다"는 변형 검사가 생성형 문장에서는 무의미하다 — 코드 확인

`different` 관계는 값이 조금만 달라도 통과한다. 생성형 문장은 매번 달라지므로
사실상 항상 통과한다. 결정적 필드나 추출한 값에만 허용한다.

근거: [bundle_evaluation.py:478](../src/replica_mvp/bundle_evaluation.py#L478)

#### C6 · P2 · 의존성 버전을 관측하지 못해도 재현 판정에 반영되지 않는다 — 재현

의존성 관측은 설치 버전을 확인할 뿐 실제 호출 증거가 아니다(코드 주석에 명시).
완료 판정은 `different`만 gap으로 넣고 `unverified`는 넣지 않는다. 다른 조건이 모두
통과하면 `unverified`여도 `reproduced`가 나온다. 기능 충실도에 필수인 의존성과 선택적
버전 메타데이터를 구분하고, 필수 동작은 실행 근거로 확인한다.

근거: [completion.py:480](../src/replica_mvp/completion.py#L480),
[bundle_runtime.py:212](../src/replica_mvp/bundle_runtime.py#L212)

#### C7 · P2 · Operator가 봉인 테스트를 볼 수 있다 — 오염 위험

`claim.json`에 선택 시나리오의 `tests`와 `evaluation.additional_cases`가 그대로
들어간다. Builder용 문맥에서는 제거되지만, Operator 쪽 차단 장치는 "지시에 넣지
말라"는 Skill 규칙뿐이다. Builder에게 정답이 유출됐다는 증거는 아니다. Operator용
공개 claim을 분리하고, 봉인 자료는 평가 보관소에만 둔다.

근거: [agent_harness.py:206](../src/replica_mvp/agent_harness.py#L206),
[replica-operator-agent/SKILL.md:164](../.claude/skills/replica-operator-agent/SKILL.md#L164)

#### C8 · P2 · 개발 루프 통과가 Builder 자기보고이고, 프로토콜이 병목이다 — 코드 확인, Delphi 기록

개발 루프의 통과는 Builder가 보낸 JSON의 형식과 개수로만 판정한다. 최종 판정은 봉인
평가가 따로 하므로 **평가 전체가 자기보고를 믿는 구조는 아니다.** 다만 수정 예산이
자기보고로 소진되거나 종료된다. Delphi 세 claim은 모두 세 번째 시도에서 구현 결함이
아니라 "validated direct feedback not completed"로 `EXECUTION_ABORTED`됐다. 하네스가
Builder의 테스트 명령을 직접 실행해 판정하면 수명주기 상태도 줄일 수 있다.

근거: [agent_execution.py:369](../src/replica_mvp/agent_execution.py#L369),
로컬 `work/delphi-ai/implementation-check-2026-09-08/agent-run/agent-harness.json`

#### C9 · P2 · 테스트 종류 분류가 둘로 갈린다 — 코드 확인

개발 루프는 `{normal, boundary, negative, structural}`, 완료 판정은
`{normal, boundary, insufficient_information, novel}`을 쓴다. 평가 준비기는 종류가
없으면 사례 id 문자열에서 추측한다.

근거: [agent_execution.py:20](../src/replica_mvp/agent_execution.py#L20),
[completion.py:11](../src/replica_mvp/completion.py#L11),
[bundle_evaluation.py:78](../src/replica_mvp/bundle_evaluation.py#L78)

### ④ 사용·문서·운영

#### D1 · P1 · 상태와 다음 입력의 책임이 없어 연속 사용이 완성되지 않는다 — 설계 공백

`bundle_session`은 임시 작업 공간을 만들고 끝나면 정리한다. 한 호출 안의 여러 입력과
명시적 파일 재첨부는 지원하지만, 다음 CLI 호출에서 사용자 상태를 다시 여는 계약은
없다. 인터뷰 재개, 대화 이력, Actions 승인 대기·예약·중복 억제가 호출 사이에
이어진다는 보장이 없다. 상태가 필요한 기능에는 `session_id`, 상태 위치, 재개 방식을
계약화한다. 평가용 격리 실행은 유지한다.

근거: [bundle_runtime.py:241](../src/replica_mvp/bundle_runtime.py#L241),
[bundle_evaluation.py:895](../src/replica_mvp/bundle_evaluation.py#L895)

#### D2 · P2 · 공개 번들과 체험 CLI의 계약이 맞지 않는다 — 앞선 검토에서 재현

공개 `replica-spec/v1`에는 `evidence_policy`가 없고 출력 계약이 설명 문자열이다.
질문형 체험은 `built Replica has an invalid evidence policy`, JSON 체험은
`Replica spec has no output contract`로 모델 실행 전에 실패했다. 별도의 `run-replica`
JSON 경로는 동작한다.

근거: [bundle_evaluation.py:720](../src/replica_mvp/bundle_evaluation.py#L720),
[experience.py:170](../src/replica_mvp/experience.py#L170),
[experience.py:351](../src/replica_mvp/experience.py#L351)

#### D3 · P2 · 문서와 실행 경로가 맞지 않는다 — 문서·구조

- README는 "저장소 자체가 Codex나 모델 API를 호출하지 않는다"고 설명한다. 실제로는
  최종 평가 Judge와 번들 실행이 모델 CLI를 호출하고, `openai_grounded_model.py`는
  OpenAI API를 직접 호출한다.
- README는 목표를 "제한된 텍스트 입출력 기능"으로 설명하지만, 완료 기준 문서는
  전체 고객 워크플로우를 목표로 한다.
- 옛 프롬프트 하네스, JSON 전용 부품, Agent 번들의 구현 경로 세 개가 공존한다.

근거: [README.md:47](../README.md#L47), [README.md:54](../README.md#L54),
[openai_grounded_model.py:10](../src/replica_mvp/openai_grounded_model.py#L10)

#### D4 · P2 · 집계가 상세 상태와 어긋난다 — 기록 확인

- 9/8 보완본은 ready claim이 3개인데 상단·하단 집계는 ready 2개/partial 1개다.
- 하네스의 `completed_claim_count`는 실행 결과가 아니라 Agent 쌍 생성을 센다. 세
  claim이 모두 중단됐는데 `completed 3, failed 0`으로 남았다.
- 집계는 claim 상태에서 계산·검증한다. `실험 종료`, `구현 준비`, `계약 통과`,
  `고객 작업 재현`을 별개 상태로 보여준다.

근거: [agent_harness.py:543](../src/replica_mvp/agent_harness.py#L543)

#### D5 · P2 · 실행 증거가 저장소 밖에 있다 — 운영

`work/`는 Git 제외 대상이다. research와 실행 증거가 이 컴퓨터에만 있어 팀원이 검증할
수 없다. 커밋된 Delphi 결과 문서는 로컬 절대경로 링크 6곳을 담고 있다. research와
요약 증거(결과 JSON, 해시)를 보존할 위치를 정한다.

#### D6 · P2 · 생성된 코드가 사용자 환경변수 전체를 받아 실행된다 — 보안

번들과 모델 명령이 `os.environ` 전체를 상속한다. manifest에 선언한 변수만 전달하도록
제한한다. 임시 작업 디렉터리는 OS 샌드박스가 아니라는 점은 이미 문서에 있다.

근거: [bundle_runtime.py:73](../src/replica_mvp/bundle_runtime.py#L73),
[bundle_runtime.py:262](../src/replica_mvp/bundle_runtime.py#L262)

## 3. 이전 지적의 보정

| 이전 표현 | 보정 |
|---|---|
| 테스트 3개 요구가 한 트랜잭션 계약으로 수렴하게 만든다 | 과장. 3개는 최솟값이다. 축소 요인은 좁은 조건을 정당화하는 지침과 단계 대응 부재다(B1). |
| Operator에게 봉인 테스트가 노출된다 | 오염 위험이다. Builder로의 정답 유출 증거는 없다(C7). |
| 하네스가 다음 시나리오로 넘어가지 않는다 | 명시된 정책이다. 남은 문제는 계약 작성 지침과의 문서 모순이다(B7). |
| 준비 부족인데 실행을 허용한다 | 최종 판정에는 gaps가 반영된다. 문제는 비용 낭비와 늦은 차단이다(B6). |
| 개발 루프가 자기보고다 | 최종 판정은 봉인 평가가 따로 한다(C8). |
| 사례 하나가 시간 초과되면 서버 종료로 연쇄 실패한다 | 더 정확히는 사례 시간 초과가 `budget_exhausted`로 분류되어 이후 사례를 건너뛴다(C2). |

## 4. 유지해야 할 장치

- 번들 파일·해시 결속, 평가 계획과 공개 runtime 계약의 해시 검증
- 봉인 평가 보관소와 공개 결과의 분리, 상세 채점 근거 비공개
- 제출 3회 제한, 같은 후보 재제출 금지, 실패 시도와 예산 이력 보존
- 반복 실행 평가, 별도 공개 예시, 구현 충실도 검토
- 사후 준비 평가 표시, 구현 준비와 최종 성공의 분리
- 폐기된 1차 점수 필드의 거부
- 결과를 부풀리지 않은 Delphi 부분 재현 판정

registry의 읽기-수정-쓰기에 잠금이 없다는 점은 결함으로 확정하지 않았다. 현재
orchestration Skill은 단일 Replica Agent가 registry를 소유하고 변경 명령을 순차
실행하도록 규정하며, 이를 어긴 실제 병렬 쓰기 경로는 확인하지 않았다.

## 5. 수정 순서와 완료 조건

| 순서 | 항목 | 완료 조건 |
|---|---|---|
| ① 1차 완료 검증 | A1, A2, A3 | 후보 누락, 미수행 배정, 완료 조사 재실행이 모두 거부된다. 정상 입력은 기존처럼 통과한다. |
| ② 2차 계약과 시작 전 검증 | B1~B7 | 현재 Delphi 인터뷰 입력에서 최초 질문·후속 질문·재개 단계의 누락이 구현 전에 검출된다. 번들 필드가 worker 산출물로 생긴다. 새 근거 없는 판정 번복과 필수 gap이 활성화 전에 차단된다. |
| ③ 평가와 판정 | C1~C9 | 통과 없는 후보가 부분 재현으로 표시되지 않는다. 사례 시간 초과와 예산 소진이 구분된다. 격리 사례와 sequence 사례가 분리된다. 효과 없는 정상 응답이 파일 없이 통과하고, 실행 완료를 주장하면서 기록이 없으면 실패한다. |
| ④ 사용·문서·운영 | D1~D6 | 공개 파일만으로 문서의 체험 명령이 동작한다. 같은 세션을 다시 열어 이어간다. 문서·CLI·Skill이 같은 경로와 권한을 안내한다. |

### 2차 완료 전에 요구할 결과물

| 내용 | 필요한 판단 | Delphi에서의 예 |
|---|---|---|
| 고객 작업의 시작과 끝 | 사용자가 처음 주는 정보와 최종 얻는 결과 | 전문 분야·주제로 시작해 답변으로 지식을 축적 |
| 필수 단계와 상태 | 시스템이 수행할 단계, 호출자의 선행 책임, 중단·재개 | 질문 생성, 답변 처리, 다음 질문, 저장 |
| 근거와 미확인 | 공개 동작·Replica 설계 선택·비공개 세부사항 구분 | 진행률 공식은 미확인, 다음 질문은 재현 대상 |
| 실제 구현 경로 | 확인된 실행 경로와 단순히 발견한 자료의 구분 | 모델+저장소+재개 가능한 CLI |
| 범위 축소 영향 | 제외 단계가 고객 목적을 훼손하는지 | 답변 한 건의 요약기로 좁히면 상위 인터뷰는 부분 범위 |
| 평가와 공개 사용 | 단계별 성공·실패·효과 부재, 새 입력, 체험 명령 | 빈 답변에는 되묻기, 저장한 지식은 재조회 |

### UI 없이 확인할 대표 흐름

- **인터뷰.** 주제로 시작하면 시스템이 첫 질문을 제시한다. 답변 내용에 따라 후속
  질문이 달라진다. 불충분한 답변에는 보충 질문을 하고 지식을 지어내 저장하지 않는다.
  종료 후 같은 세션을 다시 열어 이어간다. 저장한 지식을 식별자로 다시 조회한다.
- **지식 대화.** 자료를 등록하고 여러 차례 질문한다. 앞 질문을 참조하는 후속
  질문에 맞게 답하고, 자료를 갱신하면 새 사실을 반영한다. 사용자가 이력을 손으로
  조립하지 않아도 된다.
- **Actions.** 확인이 필요하면 실제 작업 없이 되묻고, 승인 전에는 실행하지 않는다.
  승인 후 로컬 효과를 남기고, 같은 이벤트를 다시 보내거나 재시작해도 완료한 작업을
  중복 수행하지 않는다.

이 흐름은 향후 계약 보완의 수용 조건이며, 이번에 구현하거나 통과시켰다는 뜻이
아니다. Delphi 내부 스키마·문구·진행률·원제품 품질과의 동일성은 요구하지 않는다.

## 6. 남은 검증 한계

- 2026-09-24에 Delphi 공식 [Interview Mode](https://www.delphi.ai/blog/interview-mode)와
  [Actions](https://www.delphi.ai/blog/delphi-actions) 소개 페이지를 다시 확인했다.
  과거 research가 인용한 인터뷰 도움말과 no-answer 설정 도움말의 URL은 Page Not
  Found를 반환했다. 이것만으로 과거 인용을 거짓으로 판단하지 않았다.
- 원서비스 계정 대조 실험, 실제 외부 메시지 전송, 운영 규모·장기 안정성·보안 전수
  점검은 수행하지 않았다.
- B4·B5는 지침과 책임의 공백을 확인한 것이며, 이로 인한 실제 실패 사례는 재현하지
  않았다.

## 7. 조치 결과 (2026-09-25)

커밋 `e069fb6`, `be1df2a`, `955f4ec`, `b97e83c`. 자동 테스트 290개와 `team-ai guard`가
통과했다. 새 Agent 실행이나 실제 모델 호출은 하지 않았다.

| 항목 | 조치 | 커밋 |
|---|---|---|
| A1 | 체크포인트 후보마다 `candidate_resolutions`(유지·병합·제외+사유)를 요구하고, 최종 claim이 후보나 승격된 deferred에서 나왔는지 확인한다. 후보 5개·`claims=[]` 입력이 이제 거부된다. | `e069fb6` |
| A2 | 배정 항목은 `completed`에 있거나 `progress.skipped`에 사유와 함께 있어야 한다. | `e069fb6` |
| A3 | `pass_1_running`·`pass_1_complete`가 아니면 `finalize-pass-1`을 거부한다. | `e069fb6` |
| B1 | 선택 시나리오의 `step_coverage`가 1차 `workflow.steps`를 모두 `implemented`·`external_dependency`·`excluded`·`unconfirmed`로 대응해야 한다. `unconfirmed`나 누락은 구현 전에 거부되고, `excluded`는 부분 범위로 기록되어 최종 결과가 `partially_reproduced`를 넘지 않는다. 좁은 조건을 정당화하던 지침 문구를 바꿨다. | `be1df2a`, `955f4ec` |
| B2 | worker 계약과 출력 템플릿에 시나리오 선택, `experiment_budget`, `evaluation`, `experience`, `step_coverage`를 넣었다. | `be1df2a` |
| B3 | 2차 fragment와 판정이 다르면 `second_pass.revisions`(이전 판정·사유·시각·인용 있는 새 출처)를 요구한다. 모든 출처에 비어 있지 않은 인용을 요구한다. 요약 집계가 claim readiness와 다르면 거부한다. | `be1df2a` |
| B4 | 자료 발견과 실행 경로 확인을 구분하도록 worker 지침을 고쳤다. | `be1df2a` |
| B5 | `merged` claim은 조사된 부모를 `merged_into`로 가리켜야 하고, 부모 계약의 `step_coverage`가 흡수한 단계도 대응해야 한다. | `be1df2a` |
| B6 | 구현 전에 1차 확정·2차 완료, 여섯 findings 종결, 경계 상태, 필수 테스트 종류를 확인한다. 평가 plan에 gap이 있으면 claim이 `RESEARCH_INCOMPLETE`로 등록되어 Agent 쌍을 시작할 수 없고, 보완으로 gap을 닫으면 `PENDING`으로 돌아간다. | `be1df2a` |
| B7 | worker 계약과 SKILL의 실행 순서 설명을 하네스 정책(선택 시나리오 하나, 대체 없음)에 맞췄다. | `be1df2a` |
| C1 | `partially_reproduced`는 통과한 봉인 사례가 하나 이상일 때만 쓴다. | `955f4ec` |
| C2 | 사례 제한 시간 초과는 `case_timeout`으로 그 사례만 실패하고, 전체 예산이 제한 요인일 때만 `budget_exhausted`다. | `955f4ec` |
| C3 | 사례마다 새 세션에서 실행하고, 상태가 필요한 흐름은 같은 `session` 이름으로 선언한다. | `955f4ec` |
| C4 | `output_artifacts`에 `when {path, in}` 조건을 둔다. 조건 밖의 응답은 파일 없이 통과하고 파일 경로를 내면 실패한다. | `955f4ec` |
| C5 | 결정적 필드(`equals` 검사, `exact` 반복, 출력 파일)가 아닌 곳의 `different` 관계는 research gap이다. | `955f4ec` |
| C6 | 버전을 관측하지 못한 의존성은 `reproduced`를 막는 gap이다. | `955f4ec` |
| C7 | 봉인 테스트·평가 사례를 Operator용 `claim.json`에서 빼서 `evaluator-vault/<claim>/claim-sealed.json`에 두고 해시로 결속했다. | `955f4ec` |
| C8 | **보류.** 아래 참고. | — |
| C9 | 평가 사례 종류를 한 어휘로 통일하고, id에서 종류를 추측하지 않는다. 개발 루프의 테스트 분류는 Builder 개발 테스트용으로 별도 유지한다. | `be1df2a`, `955f4ec` |
| D1 | `run-replica --state-dir`로 실행 디렉터리를 보존해 다음 호출에서 같은 상태를 연다. Operator Skill에 상태를 실행 디렉터리 아래에 두라고 명시했다. | `b97e83c` |
| D2 | 공개 번들의 `replica-spec.json`에 `evidence_policy`를, 시나리오에 `experience`가 있으면 `experience.json`을 공개한다. `experience --input`이 번들 출력을 JSON으로 표시한다. | `b97e83c` |
| D3 | README의 모델 호출 설명, 목표 범위, 세 구현 경로의 역할을 바로잡았다. 경로 통합은 하지 않았다. | `b97e83c` |
| D4 | 하네스 카운터를 `linked_pair_count`·`creation_failed_count`로 바꾸고, 종료 시 claim 최종 상태별 개수를 기록한다. 연구 요약 집계 불일치는 B3처럼 거부한다. | `be1df2a` |
| D5 | Delphi 9/8 요약 증거와 SHA-256을 [docs/evidence/delphi-ai-2026-09-08](evidence/delphi-ai-2026-09-08/README.md)에 두고 절대경로 링크 6곳을 바꿨다. 봉인 평가 자료와 300 MB 공개 run 전체는 복사하지 않았다. | `b97e83c` |
| D6 | 생성된 코드에는 기본 변수(PATH·HOME·로케일·TMPDIR 등)와 manifest에 선언한 변수만 전달한다. Judge CLI는 인증을 위해 기존 환경을 유지한다. | `b97e83c` |

### 보류: C8

개발 루프의 통과를 하네스가 직접 실행해 판정하려면 Operator/Builder 프로토콜 메시지,
실행 상태 스키마, Codex·Claude 양쪽 Skill을 함께 바꿔야 한다. 최종 판정은 이미 봉인
평가가 독립적으로 하므로, 자기보고가 거짓 성공으로 이어지지는 않는다. Delphi 세 claim의
중단 원인("validated direct feedback not completed")도 자기보고가 아니라 프로토콜 수명주기
문제여서, 판정 방식을 바꿔도 해결된다는 근거가 없다. 다음 전체 Agent 실행에서 같은
중단이 반복되면, 그 실행 기록을 근거로 프로토콜과 함께 재설계한다.

### 남은 일

- 현재 Delphi `research.json`은 새 파서에서 `step_coverage` 누락으로 거부된다. 9/8
  보완본은 집계 불일치와 인용 없는 출처로 거부된다. 다시 구현하려면 2차를 새 worker
  계약으로 다시 돌리거나 보완해야 한다. 특히 인터뷰는 최초 질문·후속 질문·재개 단계를
  `implemented`로 계약하거나, `excluded`와 사유를 기록해 부분 범위로 남겨야 한다.
- D1은 호출 사이 상태를 이어 가는 실행 경로를 제공한 것이다. 기존 Delphi 번들이 상태를
  실행 디렉터리 아래에 저장하는지는 확인하지 않았다. 새 구현에서 확인해야 한다.
- 세 구현 경로의 통합(D3)과 C8은 별도 작업이다.

## 8. `03a298f` 재검토 후속 조치 (2026-09-26)

`03a298f` 재검토에서 확인된 공통 워크플로우의 빈틈 4개를 고쳤다.

| 문제 | 조치 |
|---|---|
| P1 · 2차 판정이 없는 claim을 건너뛰고 나머지만 구현으로 넘김 | 모든 1차 claim에 유효한 readiness·handoff 판정이 없으면 `RESEARCH_INCOMPLETE`로 전체를 거부한다. |
| P2 · 2차 원본(fragment)이 없으면 판정 변경 검사를 건너뜀 | 파일 경로로 여는 하네스 경로(`agent-harness-init`)에서는 모든 claim의 `run.fragment`가 조사 디렉터리 안에 있어야 하며, 없으면 검증 불가로 거부한다. 메모리 입력만 받는 Python API(`fragment_root=None`)는 파일을 볼 수 없어 이 검사를 하지 않는다. |
| P2 · "효과 없음" 응답이 경로만 숨기고 실제로 저장해도 통과 | 조건부 산출물의 `when`에 `unchanged` 저장 위치를 필수로 하고, 조건 밖 응답이면 입력 실행 전후 스냅샷이 같아야 통과한다. 봉인 평가·공개 예시·`run-replica`에 모두 적용한다. |
| P2 · `--state-dir` 재개 때 같은 입력 파일을 다시 주면 실패 | 재개 시 내용이 같은 입력은 재사용하고, 다르면 교체하며, 구현 파일과 같은 이름이면 계속 거부한다. |

남은 한계: 저장 위치 검사는 2차가 선언한 위치만 본다. 선언하지 않은 곳에 쓰는 부작용은
여전히 구현 검토가 확인해야 한다.

