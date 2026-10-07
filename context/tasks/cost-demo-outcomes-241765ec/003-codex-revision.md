**수정 권고는 `bundle_session`을 이용한 Actions 다중 턴 시연부터 만드는 것이다.** 첫 결과는 비용·실제 조작 기록·된 것과 안 된 것을 함께 제공하되, 기존 completion·봉인 평가·harness·회사 집계는 변경하지 않는다.

기존 판단 기준은 유지한다. 이번 수정에서는 **작업 단계의 보존 여부로 조작 경계를 선택하고, 측정값의 정확성과 측정 범위의 완전성을 구분**한다. 아래는 002 검토를 반영한 권고이며 사용자 확정안이나 실행 결과가 아니다. 002의 `CDO-14` 참조는 본문 `CDO-13`을 가리키는 오기로 처리한다.

**CDO-07 — 누락 보완은 수용, “48이 잘못된 실측값”이라는 해석은 기각한다.**

보존된 영수증에는 `input_tokens: 48`, `cache_read_input_tokens: 1400785`, `cache_creation_input_tokens: 79049`가 함께 있다. 48 자체를 잘못 측정했다는 근거는 없다. 문제는 현재 필터가 캐시 항목을 버리고, 남은 값을 전체 입력 사용량처럼 읽게 할 수 있다는 것이다. [영수증](/Users/cho/replica-mvp/work/delphi-ai-v2/demo-session/orchestration/chat-result.json), [bundle_runtime.py:181](/Users/cho/replica-mvp/src/replica_mvp/bundle_runtime.py:181)

- 새 helper는 원본 `usage`, `modelUsage`, 요청 모델, 관측 모델을 보존한다. 관측 모델이 없으면 요청 모델로 대신 채우지 않는다.
- 첫 합산 단위는 **새 데모의 개별 CLI 호출 최종 영수증**이다. `usage`를 항목별 집계 원본으로 사용하고 `modelUsage`는 모델별 설명 자료로 둔다. 둘을 더하지 않는다.
- 캐시 세부 항목과 상위 항목, 생각 토큰과 출력 토큰의 포함 관계를 확인하지 않고 합산하지 않는다. provider·버전별 의미가 불명확하면 전체 토큰 합계를 만들지 않는다.
- 실패·중단 호출도 원시 출력을 보존하되, usage가 없으면 `unknown`이다. 누적 세션 영수증인지 불명확한 값도 호출별 합계에서 제외한다.
- 영수증 없는 Builder 자기보고는 `self_reported` 출처로 구분하고 실측 합계에 넣지 않는다.
- **첫 구현에서는 기존 `native_model_judge`를 교체하지 않는다.** 새 테스터·판정에 helper를 적용하고, 기존 판정 계측 개선은 후속으로 분리한다.

**CDO-08 — PATH shim은 조건부 수용한다. 투명성은 아직 미검증이다.**

Actions는 `claude`를 PATH로 호출하고 내부 재시도와 병렬 실행을 한다. 계측 지점으로 적절하지만, 래퍼가 시간초과·종료 동작을 바꿀 수 있다. [delphi_actions.py:53](/Users/cho/replica-mvp/work/delphi-ai-v2/demo-session/actions/engine/delphi_actions.py:53), [delphi_actions.py:958](/Users/cho/replica-mvp/work/delphi-ai-v2/demo-session/actions/engine/delphi_actions.py:958)

최소 구현은 다음으로 제한한다.

1. PATH 변경 **전에** 실제 CLI 절대경로를 확정한다. 래퍼는 그 경로로 실행하여 자기 자신을 다시 호출하지 않는다.
2. 엔진 단계별 임시 래퍼에 실제 경로·영수증 디렉터리·부모 단계 ID를 넣는다. 후보 파일과 manifest는 바꾸지 않는다.
3. `bundle_session`에 선택적 command runner 연결점만 추가한다. 데모 helper가 전달받은 환경의 PATH만 바꾸며, 전역 `os.environ`은 변경하지 않는다. 기본 runner 동작은 유지한다.
4. 별도 환경변수로 영수증 경로를 넘기는 방식은 피한다. 현재 필터는 기본 목록과 manifest 선언 변수만 전달하므로 새 변수가 빠진다. [bundle_runtime.py:33](/Users/cho/replica-mvp/src/replica_mvp/bundle_runtime.py:33)
5. 호출마다 고유 디렉터리에 시작 기록, 원시 stdout·stderr, 종료 기록을 저장한다. 병렬 호출이 하나의 파일에 동시에 append하지 않게 한다.
6. argv·stdin·cwd를 보존하고 stdout·stderr는 원시 바이트로 전달한다. 계측 메시지를 두 스트림에 섞지 않는다. 종료코드·signal·시간초과와 하위 프로세스 정리를 검증한다.
7. 시작 기록만 남거나 출력이 끊기면 `incomplete`로 표시한다. 강제 종료로 시작 기록조차 누락될 수 있는 구간은 부모 실행 기록에 남기며, 전체 호출 수를 안다고 주장하지 않는다.

**통과 조건:** 결정적 가짜 CLI로 직접 실행과 래퍼 실행의 입력 전달·출력 바이트·종료 상태를 비교하고, 병렬·실패·중단·고아 프로세스 여부를 확인한다. 이어 같은 후보·초기 상태·입력·의존성 조건에서 계측 전후 사례를 비교한다. 실모델 비교는 미리 고정한 의미·파일 효과 기준을 사용하며, 문장 차이만으로 계측 영향이라고 단정하지 않는다.

소스 해시 불변은 행동 불변의 증거가 아니다. 투명성 검증이 실패하거나 차이 원인을 분리하지 못하면 **shim을 끄고 새 상태에서 다시 실행**한다. 그 실행의 내부 모델 비용은 `unknown`, 계측 범위는 `partial`로 남긴다. 문제가 있는 shim을 유지한 채 coverage만 낮추거나 후보를 고쳐 맞추지는 않는다.

절대경로 CLI·직접 HTTP는 이 방식의 범위 밖이다. 기록에는 `path_resolved_claude_cli`라는 범위를 명시한다.

**CDO-09 — 수용한다. 001의 가격 환산 일괄 제외를 수정한다.**

세 영수증에서 `costBasis: list`와 정가 환산액 약 **$1.483 / $0.993 / $1.546**을 직접 확인했다. 이는 CLI가 제공한 추정액으로 유용하다. [chat](/Users/cho/replica-mvp/work/delphi-ai-v2/demo-session/orchestration/chat-result.json), [interview](/Users/cho/replica-mvp/work/delphi-ai-v2/demo-session/orchestration/interview-result.json), [actions](/Users/cho/replica-mvp/work/delphi-ai-v2/demo-session/orchestration/actions-result.json)

- 표에는 **실제 청구액 / CLI 정가 환산 추정액 / 미측정**을 구분한다. 새 가격표 조회나 자체 계산은 하지 않는다.
- 위 과거 값은 `session_conversion`, `estimated`로 별도 표시한다. 원래 제작 전체 비용이나 새 시연 합계에 넣지 않는다.
- 과거 영수증과 현재 후보의 정확한 버전 연결이 확인되지 않으면 그 한계도 적는다.
- 추정액을 실제 금액 상한 집행에 사용하지 않는다. 첫 실행 제한은 시간·테스터 행동 수이며, shim을 사용할 때 포착 가능한 내부 호출 수도 제한한다.
- 실제 금액 상한을 요구했지만 계측할 수 없다면 `budget_unverifiable`로 처리한다. [resources.py:107](/Users/cho/replica-mvp/src/replica_mvp/resources.py:107)

**CDO-10 — 중복 위험은 수용하고, “최신 결과 하나면 기업 비용이 완전하다”는 해석은 기각한다.**

이전 개발 기록을 후속 결과에 붙이는 코드를 확인했다. 그러나 최신 결과만 선택하면 이전 평가 비용까지 모두 포함된다는 보장은 없다. [bundle_evaluation.py:899](/Users/cho/replica-mvp/src/replica_mvp/bundle_evaluation.py:899)

첫 결과에서는 기존 결과 폴더를 합산하지 않는다. 새 실행의 고유 `call_id`별 영수증만 한 번 집계하고 부모 단계 요약은 다시 더하지 않는다. helper와 shim이 같은 호출을 관측하면 같은 ID로 결합한다. 과거 자료는 참조 표로만 둔다.

제작·시연·검증용 사전 실행도 구분한다. 병렬 호출 시간 합계와 전체 경과 시간을 따로 표시하며, `num_turns`를 CLI 호출 수로 바꾸지 않는다.

**CDO-11 — 수용한다. 첫 조작 경계를 엔진 JSON 프로토콜로 변경한다.**

`play.py`도 턴마다 같은 엔진을 호출한다. `bundle_session`의 stdio 경로는 같은 작업 디렉터리에서 호출을 반복할 수 있다. 따라서 JSON이라는 이유로 작업이 축소되는 것은 아니다. [play.py:84](/Users/cho/replica-mvp/work/delphi-ai-v2/demo-session/actions/play.py:84), [bundle_runtime.py:290](/Users/cho/replica-mvp/src/replica_mvp/bundle_runtime.py:290)

첫 계획은 승인·거절 두 사례로 제한한다.

- 공개·합성 연락처 준비 → 자연어 지시 등록 → 이벤트 → 승인 대기 조회 → 승인 또는 거절 → 저장 결과 확인.
- AI는 매 턴 실제 응답을 받고 다음 요청을 만든다. `pending_id`는 앞선 응답에서 얻으며 임의 생성하지 않는다.
- 실행기는 허용 action·단계·고정 사실을 검증한다. AI에게 셸·파일 수정 권한을 주지 않는다.
- 사례별 상태는 분리하고, 사례 안에서는 유지한다. 원시 입출력과 파일 관측은 실행기가 남긴다.
- 승인은 outbox 내용과 상태 변화를 확인한다. 거절은 **검토 직전 대비 outbox·연락처의 불필요한 효과가 없는지** 확인하되, pending 기록이 rejected로 바뀌는 정상 저장은 허용한다. [delphi_actions.py:1000](/Users/cho/replica-mvp/work/delphi-ai-v2/demo-session/actions/engine/delphi_actions.py:1000)

보고서에는 `interaction_surface: engine_json`을 표시한다. 사람용 CLI 화면·실제 이메일 발송·전체 Actions 기능을 검증했다고 표현하지 않는다. 화면 조작은 첫 결과 이후 필요성이 확인될 때 추가한다.

**CDO-12 — 출처 경계는 수용, 봉인 입력 해시 비교는 첫 구현에서 기각한다.**

첫 공개 시연은 과거 vault를 읽을 이유가 없다. 해시 일치 검사도 변형된 사례의 유출을 잡지 못하므로 이를 위해 비공개 자료 의존성을 추가하지 않는다.

계획은 공개 조사 근거·공개 예시·합성 입력에서 작성하고 입력 자료 목록을 남긴다. 공개 예시나 구현 manifest 자체를 원제품의 정답 근거로 격상하지 않는다. 기대 조건에는 공개 규칙인지 우리 실험 조건인지 표시한다.

`case_author`, 계획 해시·고정 시각, 후보 해시, `retrospective`를 기록한다. 기존 구현·의견을 읽은 노출은 되돌릴 수 없으며 독립 평가라고 부르지 않는다. 기존 봉인 결과는 유지하고 새 결과를 별도 디렉터리에 둔다. 세션 버전과 이전 평가 버전이 다르다는 근거도 유지한다. [demo-session/README.md:24](/Users/cho/replica-mvp/work/delphi-ai-v2/demo-session/README.md:24)

**CDO-13 — 수용한다. 첫 결과 전 운영 연결을 철회한다.**

첫 변경 범위는 신규 `demo.py`, 계측 helper, `bundle_runtime.py`의 선택적 연결점, CLI 명령, 필요한 테스트다. 결과 계산과 간단한 Markdown 출력도 `demo.py`에서 끝낸다.

기존 `completion.py`, boolean 판정, 봉인 기준, harness, 회사 집계, 2차 Skill은 첫 검증에서 변경하지 않는다. 새 판정만 `passed / failed / not_evaluated`를 사용한다. 실행 차단과 기능 불충족도 분리한다.

기본 공개 경로와 현행 봉인 운영 규칙의 충돌은 **후속 통합 과제**로 남긴다. 이번 독립 시연이 이를 해결했다고 표시하지 않는다. [project-direction.md:208](/Users/cho/replica-mvp/context/project-direction.md:208)

향후 사용자가 구현을 요청하면 그 범위의 일상적 선택은 자율적으로 진행한다. 002의 “사용자 확인 후”를 단계마다 재승인을 받는 관문으로 채택하지 않는다.

**수정된 최소 순서와 완료 기준**

| 순서 | 작업 | 완료 기준 |
|---|---|---|
| 1 | 공개 자료로 두 사례 계획 고정 | 출처·작성자·사후 설계·후보 버전·허용 사실·기대 조건·상한이 기록된다. |
| 2 | helper·선택적 runtime 연결·shim | 원시 출력과 실패 영수증을 보존한다. 전달 투명성·병렬·중단 검증을 통과하거나 shim을 제외한다. |
| 3 | AI 다중 턴 실행 | 두 사례가 실제 시도되고 동적 ID·상태·파일 효과가 기록된다. 실패를 숨기거나 자동 수정하지 않는다. |
| 4 | 별도 판정과 세 결과 생성 | 비용 범위, 입력→과정→출력, 충족·불충족·미평가와 근거가 함께 보인다. 사람 검토는 `pending`이다. |
| 후속 | 회사 집계·운영 연결 | 전체 주장별 결과·미실행 사유를 연결하고 공개 경로의 계약·완료 판정·Skill을 정합화한다. |

최소 산출물은 `demo-plan.json`, `events.jsonl`, `receipts/<call_id>/`, `artifacts/`, `demo-result.json`, `report.md`다. 결과의 핵심은 다음 정도면 충분하다.

```json
{
  "interaction_surface": "engine_json",
  "case_design": "retrospective",
  "plan_sha256": "<계획 해시>",
  "candidate_sha256": "<후보 해시>",
  "costs": {
    "billed_amount": null,
    "cli_list_estimate": null,
    "coverage": "partial",
    "receipt_ids": []
  },
  "cases": [{
    "id": "reject",
    "execution_status": "completed",
    "checks": [{"status": "passed", "evidence_event_ids": ["event-7"]}]
  }],
  "human_review": {"status": "pending"}
}
```

위 값은 형식 예시다. 비용 null에는 미측정 이유를 붙이고, 실제 결과에는 된 것·안 된 것·미평가 및 원인 가설을 관측 근거와 연결한다.

이번 턴에서 확인한 것은 코드 경로와 보존된 영수증의 필드다. **shim 투명성, 중단 시 손실 범위, 동적 ID를 사용하는 AI 실행, 실제 파일 효과는 추가 실행 검증이 필요하다.** 제품·모델·테스트 실행과 파일 변경은 하지 않았다. 주요 범위 축소는 수용했으며, 위 검증 조건에 대한 Claude 재검토가 남아 있다.
