**권고는 비용 기록·AI의 실제 사례 실행·관측 결과를 한 실행 기록으로 묶는 작은 흐름을 먼저 만드는 것이다.** 기존 자원 형식·번들 실행·파일 검증·기업별 집계를 재사용하되, 공개 사례를 단순 재생한 결과를 ‘AI 테스터 시연’으로 부르지는 않는다. 첫 기술 검증 대상으로 Delphi Actions를 권한다. 기업 전체 결과물의 대상 선정과는 구분한다.

판단 기준은 사용자 요구인 **세 결과 우선, 실제 작업 보존, 사례·기대 결과 사전 고정, 미측정·미평가의 명시, 기존 결과 보존**이다. 진행자의 “한 실행에서 세 결과를 함께 낸다”는 해석은 이 기준에 부합한다. 다만 AI 테스터 방식과 첫 기업은 아직 사용자 확정안이 아니다. 기존 쟁점 ID가 없으므로 아래 `CDO-01`~`CDO-06`을 제안한다.

**CDO-01 — 최소 구현 범위: 진행자의 통합 흐름을 수용한다.**

현재 필요한 기반은 상당 부분 있다.

| 확인한 구현 | 재사용할 것 | 추가할 것 |
|---|---|---|
| 자원 값에 `measured / estimated / unknown`과 근거를 저장한다. [resources.py:36](/Users/cho/replica-mvp/src/replica_mvp/resources.py:36) | 기존 측정 형식 | 호출별 기록·누락 범위·중복 없는 합산 |
| 사례별 출력·실행 시간·오류·파일·저장소 상태를 수집한다. [bundle_evaluation.py:462](/Users/cho/replica-mvp/src/replica_mvp/bundle_evaluation.py:462) | 실행 및 관측 함수 | 실제 AI 조작 기록과 공개 결과 |
| 모델·범위·일부 시간·개입·미측정을 `experiment_record`로 묶는다. [bundle_evaluation.py:683](/Users/cho/replica-mvp/src/replica_mvp/bundle_evaluation.py:683) | 기존 요약 책임 | 제작·시연·판정의 구분과 모든 시도 연결 |
| 전체 조사 주장을 실행 결과와 결합한다. [agent_harness.py:1666](/Users/cho/replica-mvp/src/replica_mvp/agent_harness.py:1666) | `company-claims.json`의 분모 | 사례·비용·확인된 것·미확인 사항 링크 |
| 기존 보고서는 `build_record`와 별도 평가 파일을 받는다. [reporting.py:371](/Users/cho/replica-mvp/src/replica_mvp/reporting.py:371) | Markdown 작성 방식 | 번들·시연 결과를 받는 보고 함수 |

새 코드의 중심은 `src/replica_mvp/demo.py` 하나와 기존 파일의 작은 연결 변경으로 권한다. 책임은 **계획 검증 → 실행 → 관측 저장 → 판정 → 결과 반환**이다. 범용 에이전트 프레임워크나 구현자 구조 개편은 필요하지 않다.

산출물은 `demo-plan.json`, `events.jsonl`, `demo-result.json`, `report.md`와 실제 입출력 파일이면 충분하다. 기존 공개 결과 디렉터리를 덮어쓰지 않고 새 실행 디렉터리에 저장한다.

**CDO-02 — 비용: 기존 형식 재사용을 수용하되, 런타임 계측만으로 제작 비용까지 측정한다는 가정은 기각한다.**

코드상 측정 경계는 다음처럼 갈린다.

- 쌍 실행의 `agent_execution.py`는 Builder 피드백에 실린 자원을 받아 저장한다. 외부 구현 세션을 직접 계측하지 않는다. [agent_execution.py:455](/Users/cho/replica-mvp/src/replica_mvp/agent_execution.py:455)
- 단일 구현 경로는 제출 시 `unknown_resources()`를 넣으며, 내부 반복과 토큰 미측정을 명시한다. [single_agent.py:121](/Users/cho/replica-mvp/src/replica_mvp/single_agent.py:121)
- 최종 판정 CLI는 일부 토큰 사용량을 수집한다. 경제적 비용이나 모든 중첩 호출을 측정하는 장치는 아니다. [bundle_runtime.py:155](/Users/cho/replica-mvp/src/replica_mvp/bundle_runtime.py:155)
- Delphi Actions 엔진은 내부 CLI를 최대 두 번 호출하고 응답 내용만 반환한다. 사용량과 내부 재시도가 상위 기록에 전달되지 않는다. [delphi_actions.py:53](/Users/cho/replica-mvp/work/delphi-ai-v2/demo-session/actions/engine/delphi_actions.py:53)

권고하는 최소 계측은 다음과 같다.

1. `events.jsonl`의 각 호출에 `event_id`, 단계, 세션·시도 ID, 시작·종료 시각, 요청 모델, 관측 모델, 원본 영수증 참조와 기존 `resources` 객체를 넣는다. 단계는 제작·복제품 실행·테스터·판정·사람 검토로 구분한다.
2. 제작 비용은 **외부 구현 세션의 실제 사용량 영수증을 연결할 수 있을 때만** 수집한다. 가져올 수 없는 구간은 누락 이유와 범위를 기록한다. 오래된 제작 비용은 새 시연 비용에 포함하지 않는다.
3. 실패·중단·재시도도 남긴다. 동일 영수증은 한 번만 합산하고, 상위 호출에 포함된 하위 사용량을 다시 더하지 않는다.
4. 전체 경과 시간과 호출 시간 합계를 구분한다. 기존 `development_to_submission_seconds`는 대기와 이전 평가까지 포함할 수 있다. 이를 순수 제작 작업 시간으로 표시하면 안 된다. [bundle_evaluation.py:705](/Users/cho/replica-mvp/src/replica_mvp/bundle_evaluation.py:705)
5. 사람 개입 목록이 비어 있다는 사실을 ‘사람 개입 0’으로 해석하지 않는다. 기존 형식은 누가·언제 했는지를 별도 필드로 받지 않으므로 이벤트 바깥 필드에 기록한다.

첫 버전에서 가격표 환산은 제외한다. **관측 토큰, 측정 시간, 확인된 과금액, 미측정 항목**만 보여 준다. 금액 상한을 사용자가 지정했는데 비용을 계측할 수 없다면 `budget_unverifiable`로 중단한다. 현재 평가기는 금액 상한이 있으면 실행을 차단하므로, 기록 추가만으로 금액 상한 집행까지 구현됐다고 주장하면 안 된다. [resources.py:107](/Users/cho/replica-mvp/src/replica_mvp/resources.py:107), [bundle_evaluation.py:528](/Users/cho/replica-mvp/src/replica_mvp/bundle_evaluation.py:528)

**CDO-03 — AI 사례 시연: 실제 조작을 채택하고, 기존 결정적 검사는 유지한다.**

현행 호출 경로는 다음까지 가능하다.

`cli.py run-replica → builder.run_built_replica → run_published_bundle → bundle_session`

이 경로는 실제 파일 입력, 여러 JSON 턴, 상태 디렉터리 재사용, 결과 파일 검증을 지원한다. 따라서 현재 구현을 “단발 JSON밖에 못 한다”고 설명하는 것도 부정확하다. 다만 transport는 `stdio_json / http_json`이며, 자연어 터미널 조작이나 브라우저 조작은 제공하지 않는다. [cli.py:374](/Users/cho/replica-mvp/src/replica_mvp/cli.py:374), [builder.py:256](/Users/cho/replica-mvp/src/replica_mvp/builder.py:256), [bundle_runtime.py:46](/Users/cho/replica-mvp/src/replica_mvp/bundle_runtime.py:46)

현재 `public_examples`는 코드가 고정 입력을 순서대로 넣는 재생이다. 최종 판정자는 후보를 실행하지 말라는 지침을 받는다. 둘을 연결해도 실제 AI 테스터가 되지는 않는다. [bundle_evaluation.py:569](/Users/cho/replica-mvp/src/replica_mvp/bundle_evaluation.py:569), [bundle_runtime.py:130](/Users/cho/replica-mvp/src/replica_mvp/bundle_runtime.py:130)

**첫 구현 권고:** 고정한 CLI 프로그램 하나를 실행하고, AI가 화면 출력을 받아 다음 입력을 선택하는 제한된 실행 루프를 만든다.

- 테스터는 대본과 허용된 사용자 정보만 받아 `입력 보내기 / 관찰 / 종료`를 요청한다. 임의 셸 명령과 구현 수정은 제공하지 않는다.
- 실행기가 실제 stdin·stdout·stderr·종료 상태를 기록한다. 테스터가 작성한 “실행했다”는 서술은 실행 증거로 사용하지 않는다.
- 단계 순서와 사용할 사실은 고정한다. 동적 질문에 답하는 경우에도 대본에 없는 사실을 만들어 성공시키지 않는다.
- 사례마다 새 상태로 시작하고, 사례 내부의 대화·승인·저장은 이어간다.
- 테스터의 기본 시도는 사례당 1회다. 실패 후 수정·재실행은 새 시도로 남긴다. 엔진 내부 재시도는 별도로 기록하거나 미측정으로 표시한다.
- 결정적 검사는 실행기가, 내용 평가는 별도 판정 호출이 담당한다. 판정 결과에는 근거 이벤트와 파일을 연결한다.

Delphi Actions의 실제 경로는 `play.py → Session.call → engine → 상태 파일`이며, 승인·거절과 `outbox` 확인까지 있다. 첫 사례는 **지시 등록 → 이벤트 → 승인 대기 → 승인 또는 거절 → 실제 저장 결과 확인**으로 권한다. [actions/play.py:84](/Users/cho/replica-mvp/work/delphi-ai-v2/demo-session/actions/play.py:84), [actions/play.py:302](/Users/cho/replica-mvp/work/delphi-ai-v2/demo-session/actions/play.py:302)

단, `play.py`까지 포함한 패키지의 해시를 고정해야 한다. 엔진 manifest만 고정하면 사람이 쓰는 입구가 검증 대상에서 빠진다. CLI 프로세스의 지속 실행·입출력 연결은 새 구현이며, 이번 검토에서 작동을 확인하지 않았다.

초안의 “JSON assertion과 관계 검사를 없앤다”는 제안은 채택하지 않는다. 파일이 실제로 존재하는지, 거절 후 저장소가 그대로인지 확인하는 기존 검사는 바로 재사용할 가치가 있다. [AI 테스터 초안:108](/Users/cho/replica-mvp/docs/ai-tester-evaluation-proposal.md:108), [bundle_evaluation.py:410](/Users/cho/replica-mvp/src/replica_mvp/bundle_evaluation.py:410)

또한 복사본·해시 검사는 OS 격리가 아니다. 현재 프로세스 실행은 `cwd`와 환경변수를 설정한다. 실행 기록에는 확인된 제한 수준만 적어야 한다. [bundle_runtime.py:91](/Users/cho/replica-mvp/src/replica_mvp/bundle_runtime.py:91)

**CDO-04 — 공개 시연과 봉인 경로: 충돌을 명시하고, 새 공개 경로를 권고한다.**

현재는 다음 제약이 결합돼 있다.

- 구현자 컨텍스트에서 봉인 자료를 제거한다. [agent_harness.py:108](/Users/cho/replica-mvp/src/replica_mvp/agent_harness.py:108)
- 공개 예시는 봉인 입력과 달라야 한다. novel·관계 시험 등이 없으면 활성화가 막힌다. [bundle_evaluation.py:268](/Users/cho/replica-mvp/src/replica_mvp/bundle_evaluation.py:268)
- 공개 결과에서 사례별 판정과 상세 이유를 제거한다. [bundle_evaluation.py:949](/Users/cho/replica-mvp/src/replica_mvp/bundle_evaluation.py:949)
- `run_published_bundle`은 이미 만들어진 `replica-result.json`을 요구한다. 새 후보를 시연하려면 먼저 기존 평가를 통과하는 경로에 의존하게 된다. [bundle_evaluation.py:1113](/Users/cho/replica-mvp/src/replica_mvp/bundle_evaluation.py:1113)

따라서 공개 필터 한 줄을 지우는 수정으로 끝나지 않는다.

권고는 **새 실행에 `public_demo` 경로를 추가하고, 기존 봉인 실행은 원형대로 보존**하는 것이다. 새 경로에서는 공개 계획을 먼저 고정하고, 고정된 후보 패키지를 직접 실행하며, 사례별 입력·출력·판정 이유를 모두 결과에 남긴다. 해시와 버전 고정은 유지한다. 기존 봉인 사례를 소급 공개하거나 기존 점수를 새 결과로 바꾸지 않는다.

공개 경로의 필수 관문은 정상·경계·정보 부족 사례, 기대 결과의 근거, 작업 단계 대응, 필요한 파일·효과 검사다. novel·관계 시험·반복 시험은 기존 봉인 모드에 유지하고 새 경로에서는 선택 사항으로 권한다. 이 변경은 실패한 기존 실행의 합격 기준을 낮추는 작업과 구분해야 한다.

**아직 해결되지 않은 운영 충돌:** 프로젝트 방향은 기본 봉인을 없애지만, 현재 AGENTS·Skill은 봉인 평가를 운영 경로로 요구한다. 방향 문서도 운영 규칙을 자동 변경하지 말라고 명시한다. [project-direction.md:98](/Users/cho/replica-mvp/context/project-direction.md:98), [project-direction.md:208](/Users/cho/replica-mvp/context/project-direction.md:208), [replica-research/SKILL.md:502](/Users/cho/replica-mvp/skills/replica-research/SKILL.md:502)

이번 턴에서는 이를 바꾸지 않았다. 후속 구현에서는 공개 경로의 계약·CLI·완료 판정·관련 Skill 설명을 함께 정합화해야 한다. 로드맵 D1~D8 전체 확정을 선행시키기보다 이번 세 결과에 필요한 결정만 먼저 반영하는 순서 변경을 권고한다.

**CDO-05 — 된 것·안 된 것: 실행 상태와 기능 판단을 분리해야 한다.**

새 결과에는 두 축이 필요하다.

| 축 | 최소 값 | 의미 |
|---|---|---|
| 실행 | 완료 / 차단 / 미실행 | 실제로 작업을 수행했는가 |
| 조건별 판단 | 충족 / 불충족 / 미평가 | 근거 있는 기대 결과와 대조했는가 |

이 구분은 표현 개선만이 아니다. 현재 `_judge`는 판정자가 없으면 `NOT_EVALUATED`를 반환하지만, 이후 사례의 `pass`는 거짓이 된다. 통과 사례가 없고 별도 실행 오류도 없으면 완료 판정은 `not_reproduced_on_this_path`가 될 수 있다. 미평가를 기능 실패로 읽을 위험이 있다. [bundle_evaluation.py:349](/Users/cho/replica-mvp/src/replica_mvp/bundle_evaluation.py:349), [bundle_evaluation.py:637](/Users/cho/replica-mvp/src/replica_mvp/bundle_evaluation.py:637), [completion.py:513](/Users/cho/replica-mvp/src/replica_mvp/completion.py:513)

또한 판정 프롬프트가 자료를 검사할 수 없는 경우에도 `pass=false`를 요구한다. 새 판정 계약은 `passed / failed / not_evaluated`를 반환하도록 바꾸고, 기존 봉인 결과 해석은 보존해야 한다. [bundle_evaluation.py:629](/Users/cho/replica-mvp/src/replica_mvp/bundle_evaluation.py:629)

보고서는 다음처럼 쓴다.

- **된 것:** 어떤 단계·조건을 어떤 이벤트와 파일로 확인했는가.
- **일부 확인됨:** 확인한 부분과 실패·미평가·제외한 부분을 각각 명시한다.
- **안 된 것:** 실행된 작업이 근거 있는 기대 조건을 어긴 관측을 제시한다.
- **실행·평가 불가:** 접근, 환경, 예산, 기준 부족, 판정 도구 문제를 적는다.

막힌 원인은 `관측 사실 / 원인 가설 / 추가 확인`으로 나눈다. “접근 거부를 받았다”는 관측에서 “독점 데이터가 기술 장벽이다”로 바로 넘어가지 않는다. 기업이 주장한 장벽은 공개 출처와 사례를 연결해 대조한다.

기업 집계는 기존 전체 주장 목록을 기준으로 한다. 한 기능의 시연 성공으로 기업 전체를 완료 처리하지 않는다. 기존 `_company_results`의 이 원칙은 유지하고, 새 시연 결과를 후보 버전과 함께 연결한다. [agent_harness.py:1666](/Users/cho/replica-mvp/src/replica_mvp/agent_harness.py:1666)

**CDO-06 — 사후 사례·버전·사람 판단: 별도 표시를 필수로 권고한다.**

Delphi 세션 데모는 기존 평가 후 규칙을 바꿨고 재평가하지 않았다고 명시돼 있다. 따라서 그 점수를 이번 시연에 가져올 수 없다. [demo-session/README.md:22](/Users/cho/replica-mvp/work/delphi-ai-v2/demo-session/README.md:22)

최소 계획에는 다음을 고정한다.

- 사례 ID·종류, 준비 파일, 사용자 행동 순서와 허용 사실.
- 기대 결과마다 근거 참조와 출처 유형: 원제품 관측 / 공개 규칙 / 별도 검증 / 우리 실험 조건.
- 겨냥하는 공개 장벽과 해당 출처. 근거가 없으면 장벽을 만들어 붙이지 않는다.
- 사례 고정 시각·해시, 기준 구현 해시, `prospective / retrospective`.
- 사례당 시도·행동 수·시간 상한, 판정자 정보.

기존 구현을 본 뒤 만든 Delphi 사례는 `retrospective`로 남긴다. 이후 수정 전에 고정했다면 그 수정에 대해서는 사전 고정이지만, 최초 구현 전 사례로 소급되지 않는다. 기존 구현을 읽은 영향이 사라졌다고 주장하지 않는다.

테스터와 판정자의 세션 분리는 기록하되, 그것만으로 독립 검증이라고 부르지 않는다. 현재 CLI도 별도 판정 프로세스라는 이유만으로 `independent`를 허용하지 않는다. [cli.py:439](/Users/cho/replica-mvp/src/replica_mvp/cli.py:439)

사람 검토는 최초 `pending`으로 남긴다. 실행·보고서 생성 완료와 사람의 대체 가능성 판단 완료는 다른 상태다.

**최소 출력 예시**

아래는 제안 형식의 발췌이며 실제 실행 결과가 아니다. 기존 `resources` 측정 항목 형식은 그대로 사용한다.

```text
demo-plan.json
events.jsonl
demo-result.json
report.md
artifacts/
```

```json
{
  "schema_version": "replica-demo-result/v1",
  "claim_id": "claim-002",
  "scenario_id": "selected-scenario",
  "plan_sha256": "<계획 해시>",
  "candidate_sha256": "<CLI와 엔진을 포함한 패키지 해시>",
  "case_design": "retrospective",
  "costs": {
    "development": {
      "status": "unknown",
      "reason": "기존 제작 세션 사용량 영수증 없음"
    },
    "demo_resource_event_ids": ["resource-001"],
    "economic_total": null,
    "coverage": "partial"
  },
  "cases": [{
    "case_id": "approval-reject",
    "execution_status": "completed",
    "checks": [{
      "criterion_id": "reject-has-no-effect",
      "status": "passed",
      "expected_basis_ref": "demo-plan.json#/cases/0/expected/0",
      "evidence_event_ids": ["event-004", "event-005"]
    }],
    "confirmed": ["거절 후 outbox 변화 없음"],
    "not_evaluated": ["실제 이메일 전송"],
    "cause_hypotheses": []
  }],
  "human_review": {"status": "pending"}
}
```

`report.md`는 **투입 자원 → 사례별 입력·과정·출력·판정 이유 → 된 것·안 된 것·미확인 → 다음 질문** 순서로 생성한다. 원본 출력이 없으면 원제품 동등성 비교를 넣지 않는다.

**구현 순서와 검증 완료 기준**

| 단계 | 변경 위치 | 완료 기준 |
|---|---|---|
| 1. 공개 계획·버전 계약 | 신규 `demo.py`, `cli.py`, 2차 계약 지침 | 출처 없는 기대 결과, 누락 파일, 변경된 계획을 검출한다. 기존 구현에는 사후 사례 표시가 남는다. |
| 2. 자원 기록 연결 | `resources.py`, `bundle_runtime.py`, 제작 자원 수신 경계 | 성공·실패·중단 호출이 남고, 누락은 null이다. 재수집해도 중복 합산되지 않는다. 금액 계측 불가와 시간 상한을 구분한다. |
| 3. 실제 AI 조작 | `demo.py`의 제한된 CLI 실행 루프 | AI가 실제 화면 출력을 받고 입력한다. 승인·거절·저장이 여러 턴에 걸쳐 이어진다. 허위 실행 서술로 통과할 수 없다. |
| 4. 판정·보고 | `completion.py`, `reporting.py`, 회사 결과 연결 | 미평가가 기능 실패로 변하지 않는다. 파일 부수효과와 로그 인용을 검증한다. 전체 주장과 미실행 사유가 보존된다. |
| 5. 실제 파일럿·운영 연결 | 새 실행 디렉터리, harness 분기와 관련 Skill | Delphi Actions 기술 검증 후, 선택한 기업의 전체 주장에 결과 또는 미실행 사유를 남긴다. 새 구현의 제작 비용은 시작부터 기록한다. |

기존 테스트 중 세션·파일·상태 보존·예산·전체 주장 집계 검사를 재사용하고, 이번에 추가하는 행동과 미평가 분류를 검증한다. 관련 검증 후 저장소 전체 `PYTHONPATH=src python -m unittest discover -s tests`와 `git diff --check`를 수행한다. 현재 테스트에도 상태 유지와 비공개 자료 분리 검사가 있지만, AI 테스터의 실제 사용 증거를 대신하지는 않는다. [test_bundle_evaluation.py:211](/Users/cho/replica-mvp/tests/test_bundle_evaluation.py:211), [test_bundle_evaluation.py:326](/Users/cho/replica-mvp/tests/test_bundle_evaluation.py:326)

이번 턴은 소스·문서·테스트 코드의 읽기 검토다. 제품 실행, 모델 호출, 테스트 실행, 파일 수정은 하지 않았다. Git 조회에서는 기존 변경을 확인했고 캐시 생성 제한 경고가 발생했다. **합의는 아직 없으며**, 다음 검토에서 우선 판단할 사항은 제한된 CLI 테스터의 구현 범위, 새 공개 경로와 기존 봉인 경로의 분기, 미평가를 보존하는 결과 계약이다.
