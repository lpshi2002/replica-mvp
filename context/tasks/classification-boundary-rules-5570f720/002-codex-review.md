수정 방향은 범용적으로 타당하지만, **현재 diff 그대로 확정하는 것은 보류**합니다. AI 자격과 전체 작업 범위를 분리하고, 독립 호출만으로 claim을 나누지 않는 원칙은 유지할 만합니다. 다만 과도한 병합을 막는 기준과 제외 관찰의 재분류 절차는 보완해야 합니다.

Claude의 “하위 지침 충돌 때문에 실행에서 지켜지기 어렵다”, “coverage 장치가 없다”는 진단은 근거보다 강합니다. 실제로는 우선순위 선언과 상당한 coverage 검증이 이미 있습니다.

검토 기준은 공개 근거에 따른 기능 경계, 필수 고객 작업 보존, 근거 없는 범위 확대 방지입니다. 기능 간 연결을 임의로 추가하지 않되 개별 기능의 필수 단계는 보존한다는 [프로젝트 방향](/Users/cho/replica-mvp/context/project-direction.md:110)을 적용했습니다. 아래 반례는 특정 기업의 관측 결과가 아닌 가상 사례입니다.

**I1 — 기각: 현재 문구만으로 실행 충돌을 단정할 수 없음**

1차 worker의 문장은 “standalone으로 제공될 때만 별도 claim을 연다”는 필요조건입니다. “standalone이면 반드시 나눈다”는 충분조건은 아닙니다. 따라서 새 규칙의 “독립적으로 유용한 고객 목적과 완료 결과도 필요하다”와 논리적으로 양립합니다. [1차 지침:70](/Users/cho/replica-mvp/skills/replica-research/agents/replica-first-pass.md:70), [SKILL:185](/Users/cho/replica-mvp/skills/replica-research/SKILL.md:185)

더구나 새 문구는 경계 규칙의 우선 적용과 **각 research assignment에 해당 절 포인터를 넣는 것**을 이미 요구합니다. worker Input 목록에 없다는 사실만으로 전달되지 않는다고 판단할 수 없습니다. “자기 지침을 먼저 읽는다”는 순서도 규칙을 따르지 못한다는 증거는 아닙니다. [SKILL:165](/Users/cho/replica-mvp/skills/replica-research/SKILL.md:165)

최소 보완으로 worker의 경계 절에 공통 규칙 링크를 넣고 중복 문장을 줄이는 것은 권합니다. 그러나 전체 규칙 복사나 별도 정책은 필요하지 않습니다. 실제 행동 차이는 동일한 관찰 자료를 준 worker 비교 전에는 미확인입니다.

**I2 — 수용: `not_workflow` 정의를 맞추되, 새 사유 신설은 불필요**

`no_ai_attribution`은 앞으로도 **독립 AI claim의 최종 탈락 사유**로 유효합니다. 지원 단계를 보존한 뒤 독립 claim은 탈락시킬 수 있으므로, 탈락 목록 자체를 없애거나 전부 보류로 바꿀 필요는 없습니다.

실제 불일치는 `not_workflow`의 설명입니다. 기존 표는 모델·플랫폼 속성·UI·구조·메커니즘을 열거하지만, 새 규칙은 “실제 작업이지만 부모 workflow와의 관계가 미확정인 지원 단계”에도 이 값을 사용합니다. [SKILL:138](/Users/cho/replica-mvp/skills/replica-research/SKILL.md:138), [SKILL:148](/Users/cho/replica-mvp/skills/replica-research/SKILL.md:148), [SKILL:194](/Users/cho/replica-mvp/skills/replica-research/SKILL.md:194)

따라서 정의를 “독립 workflow인지, 다른 workflow의 지원 단계인지 아직 확정되지 않은 관찰”까지 넓히고 worker에서 참조하면 됩니다. 검증기는 사유 문자열과 증거 필드를 검사하므로 기존 `not_workflow`로 표현 가능합니다. **코드와 enum을 늘려야 할 근거는 없습니다.** [project.py:551](/Users/cho/replica-mvp/src/replica_mvp/project.py:551)

단, 연결 가능성이 전혀 없는 비AI 기능까지 모두 보류시키면 안 됩니다. 새 규칙에 있는 가능한 부모·연결 workflow와 부족한 근거를 기록하는 조건을 유지해야 합니다.

**I3 — 수용하되 범위 축소: 없는 것은 claim 간 관계 점검·전달이며, coverage 일반이 아님**

기존 장치는 다음과 같습니다.

| 확인 대상 | 이미 존재하는 장치 | 한계 |
|---|---|---|
| 1차 수집 항목의 처리 | candidate·deferred마다 정확히 하나의 resolution 요구 | 최초 `excluded` 항목은 이 연결 검사 밖에 있음 |
| 1차→2차 단계 보존 | 추가 단계의 출처, 삭제 단계의 사유·출처 요구 | 기록되지 않은 관계 자체를 발견하지는 못함 |
| 계약의 단계 coverage | 본 claim과 병합된 claim의 모든 단계 매핑 요구 | 별도로 유지되는 claim 사이의 공유 관계는 검사하지 않음 |
| 시연 범위와 결과 | 미검증·제외 범위, 단계별 계획과 관측을 결과에 기록 | 공유 범위의 기업 전체 관계표는 생성하지 않음 |

근거: [project.py:692](/Users/cho/replica-mvp/src/replica_mvp/project.py:692), [second_pass.py:402](/Users/cho/replica-mvp/src/replica_mvp/second_pass.py:402), [second_pass.py:524](/Users/cho/replica-mvp/src/replica_mvp/second_pass.py:524), [agent_harness.py:1012](/Users/cho/replica-mvp/src/replica_mvp/agent_harness.py:1012), [agent_harness.py:1798](/Users/cho/replica-mvp/src/replica_mvp/agent_harness.py:1798)

2차 worker에도 계약 작성 후 누락을 확인하는 절차와 단계별 coverage 작성 규칙이 있습니다. 기본 하네스는 파서를 먼저 통과시킨 뒤 시연 계획을 고정합니다. 따라서 “freeze 전 coverage 확인 절차가 없다”는 일반화는 기각합니다. [2차 지침:91](/Users/cho/replica-mvp/skills/replica-research/agents/replica-second-pass.md:91), [2차 지침:403](/Users/cho/replica-mvp/skills/replica-research/agents/replica-second-pass.md:403), [single_agent.py:32](/Users/cho/replica-mvp/src/replica_mvp/single_agent.py:32)

정확한 공백은 다음 두 가지입니다.

- **관계 점검:** 모든 관찰과 별도로 유지되는 claim들을 대조해 공유 단계·전달 변형·후속 작업의 누락을 확인하는 orchestrator 절차.
- **관계 전달:** `replication_leads[].finding`에 적은 overlap 설명을 최종 보고 어디에서 읽고 보여 줄지에 대한 연결.

새 규칙 5번은 기존 `finding`과 resolution rationale를 기록 위치로 지정하므로 “기록할 곳이 전혀 없다”도 과장입니다. 다만 최종 결과 생성기는 이 관계 설명을 전용 항목으로 전달하지 않습니다. [SKILL:202](/Users/cho/replica-mvp/skills/replica-research/SKILL.md:202), [second_pass.py:716](/Users/cho/replica-mvp/src/replica_mvp/second_pass.py:716), [agent_harness.py:1941](/Users/cho/replica-mvp/src/replica_mvp/agent_harness.py:1941)

또한 현재 `outcome_counts`는 **workflow별 실험 결과 수**입니다. 코드가 이를 독립 기술 성과 수라고 선언하지는 않습니다. 기존 per-claim 집계를 중복 제거할 필요는 없으며, 공유 범위를 함께 설명하는 쪽이 맞습니다. [agent_harness.py:2008](/Users/cho/replica-mvp/src/replica_mvp/agent_harness.py:2008)

**I4 — 기각: 규칙 이동이 필수이거나 공유 기능을 표현할 수 없는 구조는 아님**

공통 경계 규칙이 수집·구현·평가에 적용되는 것은 자연스럽습니다. 해당 절도 양쪽 pass에 적용된다고 명시합니다. 5·6번을 옮기는 것보다 각 실행 위치에서 참조하고 담당 행동을 명시하는 편이 중복을 줄입니다.

2차 merge 규칙은 “독립적으로 전달되지 않는 출력”을 병합 대상으로 삼습니다. 독립 제공도 되고 다른 workflow의 단계로도 쓰이는 기능은 이 조건에 해당하지 않습니다. 별도 claim을 유지하면서 다른 claim의 `workflow.steps`에도 필요한 일을 기록할 수 있습니다. 따라서 “이분법이라 표현 불가”는 성립하지 않습니다. [2차 지침:154](/Users/cho/replica-mvp/skills/replica-research/agents/replica-second-pass.md:154)

다만 **병합하지 않은 공유 기능에서 새 근거가 발견됐을 때 다른 관련 worker를 누가 재개하는지**는 보완할 만합니다. 현재 명시적인 재개 절차는 merge 결과를 부모에게 흡수시키는 경우입니다. 이 책임을 orchestrator의 수집 완료 절차에 추가하면 됩니다. [SKILL:423](/Users/cho/replica-mvp/skills/replica-research/SKILL.md:423)

**I5 — 기각: 사례를 사용했다는 사실이 범용성 결함은 아님**

“자동화를 작성하는 에이전트”는 작성자와 실행 주체를 구별하고, “대화 내부 검색과 검색 API”는 관계가 공존할 수 있음을 설명합니다. 특정 기업명이나 전용 조건을 규칙으로 강제하지 않습니다. 두 예시는 일반 원칙을 설명하는 데 유효합니다. [SKILL:171](/Users/cho/replica-mvp/skills/replica-research/SKILL.md:171)

정리한다면 작성과 실행을 **각각** C0/C1/A1/A2로 판단한다고 명확히 하면 충분합니다. 작성 단계가 외부 고객에게 제공되는 AI 기능이라면 그 자체가 claim일 수 있고, 작성에 AI가 쓰였다는 사실만으로 실행 단계까지 AI claim이 되지는 않습니다.

**I6 — 보류: 중복 비용의 크기는 미확인, 범위 보존 원칙은 수용**

“각 workflow에 필요한 일을 포함한다”는 요구는 “같은 엔진을 매번 새로 작성한다”는 요구가 아닙니다. 기존 라이브러리·공개 서비스 등을 사용하는 경로도 가능합니다. 다른 claim의 성공을 근거로 현재 workflow 내부의 연결 검증을 생략해서는 안 된다는 취지는 타당합니다. [SKILL:191](/Users/cho/replica-mvp/skills/replica-research/SKILL.md:191), [2차 지침:420](/Users/cho/replica-mvp/skills/replica-research/agents/replica-second-pass.md:420)

claim마다 독립 구현자를 두고 셸은 데이터 공유를 하지 않는 구조는 이미 사용자 결정입니다. 이 방향을 다시 확인받을 필요는 없습니다. 공유 런타임·통합 구현자로 바꾸는 것은 별도 설계 변경입니다. [프로젝트 방향:112](/Users/cho/replica-mvp/context/project-direction.md:112)

반복 구현·조사 비용은 발생할 수 있지만 이번 검토에서는 측정하지 않았습니다. 비용이 실제 병목으로 확인될 때 재사용 구조를 검토하되, 지금은 기능 범위와 소스 코드 재사용을 구분하는 문장만 보완하면 됩니다.

**I7 — 신규·수용: 병합 기준의 추상도와 동일 문서 내 기준을 맞춰야 함**

새 3번은 목적과 완료 결과가 같으면 넓은 workflow에 흡수하도록 합니다. 그런데 뒤의 기존 설명은 동일 claim의 조건에 **시작 입력과 AI workflow까지** 포함합니다. 서로 다른 요약 기준이 남아 있습니다. [SKILL:185](/Users/cho/replica-mvp/skills/replica-research/SKILL.md:185), [SKILL:324](/Users/cho/replica-mvp/skills/replica-research/SKILL.md:324)

예를 들어 “문서를 한 번 분석해 위험 보고서를 받기”와 “변경을 지속 감시해 위험 보고서를 갱신하기”는 목적·산출물 명칭을 넓게 쓰면 같아집니다. 하지만 시작 조건, 지속 상태, 완료 조건은 다릅니다. 새 2번의 후속 workflow 구분은 이를 일부 방어하지만, 3번의 병합 문장에도 같은 기준이 연결돼야 합니다.

권고는 다음과 같습니다.

- 목적·결과 **명칭**이 같다는 이유만으로 병합하지 않는다.
- 시작 조건·처리 책임·상태·완료 조건을 대조해 같은 고객 작업의 변형인지 판단한다.
- 차이가 있다는 사실만으로 분리하지도 않는다. 독립적으로 유용한 작업이라는 근거를 요구한다.
- 기존 동일성 설명도 이 기준을 참조하도록 통일한다.

claim 수 감소 자체는 오류가 아닙니다. 독립된 작업이 사라지거나, 서로 다른 필수 조건을 하나의 성공 판정으로 덮는 것이 오류입니다.

**I8 — 신규·수용: 지원 단계 보존에는 포함 경계와 조건을 명시해야 함**

4번의 `source-supported`와 `required by that claim`은 올바른 제한입니다. 이 제한을 실제 판단 기준으로 풀어 쓰면 범위가 불필요하게 커지는 것을 막을 수 있습니다. [SKILL:194](/Users/cho/replica-mvp/skills/replica-research/SKILL.md:194)

가령 AI 답변 기능과 선택적 주간 이메일 기능이 같은 제품에 있어도, 관련 있다는 이유만으로 모든 답변 claim에 이메일 발송을 붙여서는 안 됩니다. 반대로 고객 완료 결과가 알림 수신까지라면 발송은 비AI 단계여도 보존해야 합니다.

따라서 **관계가 있다는 근거와 해당 claim의 필수 단계라는 근거를 구별**해야 합니다. 조건부 단계는 조건과 함께 보존하고, 관계 미확정 관찰은 조사 단서로 남겨야 합니다. 그 자체를 확정 workflow의 `unconfirmed` 단계로 승격해 정상 claim 전체를 막아서는 안 됩니다.

필수 지원 단계가 늘어 readiness나 최종 재현 수준이 낮아지는 것은 정확한 평가일 수 있습니다. 다만 구현에서 제외한 단계는 사유·대안·필요 자원을 기록하고 부분 범위로 실행하는 기존 경로를 활용할 수 있습니다. **단계 제외와 연구 readiness `partial`은 같은 상태가 아닙니다.** [2차 지침:452](/Users/cho/replica-mvp/skills/replica-research/agents/replica-second-pass.md:452), [second_pass.py:560](/Users/cho/replica-mvp/src/replica_mvp/second_pass.py:560), [second_pass.py:727](/Users/cho/replica-mvp/src/replica_mvp/second_pass.py:727)

**I9 — 신규·수용: excluded 재분류 시 원래 결정과 집계를 보존하는 방법이 빠져 있음**

새 6번은 exclusions까지 재검토하고 기존 deferred/resolution 과정으로 재분류하면서 원래 증거와 결정 이력을 보존하라고 합니다. 그러나 기존 excluded 예시에는 안정적인 ID와 excerpt가 없고, 검증기도 claim과 reason만 요구합니다. [SKILL:215](/Users/cho/replica-mvp/skills/replica-research/SKILL.md:215), [1차 지침:211](/Users/cho/replica-mvp/skills/replica-research/agents/replica-first-pass.md:211), [project.py:540](/Users/cho/replica-mvp/src/replica_mvp/project.py:540)

또한 최종화의 resolution 검사는 candidate·deferred ID만 대상으로 하며, excluded 목록 길이는 그대로 제외 수에 더합니다. 재분류한 항목을 기존 excluded에도 남기면 계속 제외 수에 포함되고, 삭제만 하면 이전 결정과의 연결이 사라집니다. [project.py:758](/Users/cho/replica-mvp/src/replica_mvp/project.py:758), [project.py:833](/Users/cho/replica-mvp/src/replica_mvp/project.py:833)

확정 전에는 최소한 다음 절차를 정의해야 합니다. 원래 scope·항목·제외 이유를 보존하고, 재분류 대상에 안정적인 deferred ID와 확인된 증거를 부여하고, 현재 excluded 집계와 이전 결정 이력을 구분합니다. 새 대형 스키마가 필요한 것은 아니지만 “기존 과정으로 처리한다”만으로는 부족합니다.

**확정 전 권고**

필수 보완은 경계 규칙 참조의 명확화, `not_workflow` 설명 정리, 병합 기준 통일, 지원 단계 포함 조건, excluded 재분류 절차입니다. 2차 수집 완료 시에는 기존 coverage 검사를 재사용하면서 **claim 간 관계와 누락만 추가 대조**하도록 담당·시점·기록 위치를 정하면 됩니다.

overlap 설명을 자동 생성되는 `company-claims.json`에도 반드시 노출할지는 후속 구현 범위로 구분해야 합니다. 현재 코드가 자동으로 해 주는 일처럼 표현해서는 안 됩니다. 공유 구현 구조나 새로운 기술 성과 점수는 이번 수정의 필수 조건이 아닙니다.

**검증 범위**

실제 미커밋 diff, 양쪽 worker 지침, 관련 파서·하네스·최종 결과 생성 코드를 확인했습니다. 단계 누락·미확정·제외·추가·삭제·병합 coverage에 관한 기존 테스트 **6개를 읽기 전용 설정으로 실행해 모두 통과**했습니다. 대상 파일의 `git diff --check`도 통과했습니다.

저장소 파일은 수정하지 않았습니다. 전체 테스트와 실제 research worker 실행은 수행하지 않았으므로, worker 행동 개선이나 임의 기업 전체에 대한 효과까지 검증한 결과는 아닙니다.
