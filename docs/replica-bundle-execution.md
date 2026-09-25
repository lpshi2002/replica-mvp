# Sol/Terra 구현 번들의 실행과 최종 평가

기준일: 2026-09-07. 결과 보고서 개편은 이번 수정 범위에서 제외했다.
기존 Component 보고서 경로는 유지하고, 번들 경로에는 실행과 판정에 필요한 JSON만 추가한다.

2026-09-08 모델 설정: Codex 경로의 조율 Replica Agent와 Operator는 기존 Sol에서
`gpt-6-astra`·`medium`으로 변경했다. Terra는 `gpt-5.6-terra`·`high`로 명시한다.
생성 요청에서 지정된 추론 강도를 누락하거나 다르게 요청하면 등록을 거절한다.
과거 실행 기록은 변경하지 않으며, 그 기록에 없는
실제 추론 강도를 새 기본값으로 추정하지 않는다. Claude 경로의 모델 설정은 별도다.

## 인계와 실행 경계

실제 구현은 선택된 기능마다 Agent 한 쌍을 만들어 전체 쌍을 동시에 활성화한다.
기능이 3개면 3쌍, 10개면 10쌍이며, 전체 쌍의 등록·연결을 마친 뒤 모두 활성화한다.
앞 기능의 완료를 기다리지 않는다.
`active_claim_id`는 쌍을 생성하고 연결하는 짧은 준비 구간의 잠금이고,
`max_concurrent_pairs`는 선택된 `claim_count`와 같다. `peak_active_pairs`와 claim별 시작·종료 시각으로
동시 실행을 확인한다. 조율 Agent는 registry를 바꾸는 CLI 명령을 순서대로 완료해
다른 claim의 상태를 덮어쓰지 않는다.

2차의 `handoff.selected_scenario_id`를 우선하며, 없으면 `scenario_priority`의 첫 경로를
선택한다. 둘 다 없으면 조사에 기록된 순서를 유지하고 `research_order`로 표시한다.
의존성 등급을 근거로 조사 경로를 다시 정렬하지 않는다. 선택과 우선순위가 충돌하면
진행하지 않는다. Sol은 전체 2차를 받고, Terra는 전체 workflow·findings·대안 경로와
공개 실행 계약을 받는다. 테스트·기대값·reference facts는 Terra에 전달하지 않는다.

Sol은 선택된 경로를 구체적인 파일·함수·명령·수정 작업으로 만든다. 새 기술 접근이나
범위 변경은 2차 보완에 속한다. 필요한 의존성은 실행 환경에 준비하며, 평가기가 다른
라이브러리나 모델로 바꾸거나 임의로 설치하지 않는다.

## 2차에서 준비할 평가 데이터

기존 scenario의 `tests`와 `acceptance_criteria`를 재사용한다. 기존 `expected_behavior`와
`reference_facts`는 각각 의미 평가 기준과 비공개 reference로 보존한다. 새로운 형식의
case는 기존 `replica-tests/v1`의 `id`, `kind`, `input`, `deterministic_assertions`,
`semantic_criteria`를 사용하고, `criterion_ids`로 claim의 합격 기준과 연결한다.

결정적 assertion은 `equals`, `contains`, `json_type`이다. `path: ["answer", "score"]`처럼
JSON 객체의 필드나 배열 인덱스를 지정할 수 있다. `path`를 생략하면 출력 전체를 검사한다.
`equals`는 boolean과 숫자를 구분하며, `json_type`은 object·array·string·number·integer·boolean·null을 검사한다.

scenario의 선택적 `evaluation` 예시는 다음과 같다.

```json
{
  "runtime": {"transport": "http_json", "endpoint": "/chat", "port_argument": "--port"},
  "repeat_policy": "contract",
  "timeout_seconds": 120,
  "budget": {"time_limit_seconds": 600, "cost_limit": null, "stop_on_blocked": true},
  "case_checks": {
    "normal": {
      "criterion_ids": ["criterion-001"],
      "deterministic_assertions": [{"type": "json_type", "path": ["answer"], "value": "string"}]
    }
  },
  "additional_cases": [],
  "public_examples": [],
  "assets": [],
  "output_artifacts": []
}
```

위 예시는 필드 설명용이며, 빈 novel·metamorphic·공개 예시 목록으로 `reproduced`가 되지 않는다.
실제 평가에는 다음이 필요하다.

- 정상·경계·정보 부족 case와 모든 claim 기준의 검사 연결.
- `kind: "novel"` case의 `novelty: {difference, development_inputs}`. 차이의 설명과
  개발 입력을 함께 기록한다. 동일 입력을 novel로 쓰는 것은 거절하며, 이름·숫자만 바꾼
  사례를 일반화 근거로 삼았는지는 별도 구현 검토가 확인한다.
- 불필요한 표현·순서가 바뀐 case와 핵심 사실이 바뀐 case 각각에
  `metamorphic: {case_id, relation, path, reason}`. `relation`은 `equal` 또는 `different`이며,
  비교 대상 case와 출력 필드를 명시한다. 생성형 답변 전체 대신 유지돼야 할 결정값을
  비교하고 의미적 결정 내용도 품질 기준에 넣는다.
  비교 필드가 선언된 출력 파일 경로라면 파일명 대신 보존한 파일의 SHA-256을 비교한다.
- 봉인 입력과 다른 `public_examples: [{input, description}]`.
- 실제 파일 입력이 필요하면 `assets`에 `path`, `source`, `sha256`, `media_type`,
  `provenance`, `usage_terms`, `visibility`를 기록한다. `source`는 준비된 로컬 파일이며
  `path`는 실행 디렉터리 안의 상대 경로다. 공개 재배포가 허용된 자산만 `public`으로
  표시한다. 나머지는 `evaluation_vault`다. 해시가 다르거나 파일이 없으면 성공하지 않는다.
- 최종 결과가 파일이면 `output_artifacts: [{path: ["document"], media_type: "application/pdf"}]`
  형태로 출력 JSON의 파일 경로 필드를 지정한다. 출력은 실제 상대 경로 파일이어야 한다.
  비어 있거나 실행 디렉터리를 벗어난 파일은 거절한다. 현재 파일당 한도는 100 MB다.

`stdio_json`은 `{"transport":"stdio_json"}`만 지정한다. manifest의 `command`가 JSON을
stdin으로 받아 stdout으로 JSON을 반환한다. `http_json`은 같은 command에 포트 인자를
추가해 새 로컬 서버를 실행하고 지정 endpoint에 POST한다. 기존 외부 서버 응답을 번들
실행으로 대신하지 않는다. 상태가 필요한 workflow는 같은 세션에서 유지돼야 한다.
manifest의 entrypoint는 선언된 파일이면서 command의 실제 인자여야 한다.

## 동결·평가·공개

`agent-harness-init`은 먼저 조사 완료 여부를 확인한다. 1차 확정과 2차 완료 상태, 요약
집계와 claim readiness의 일치, 여섯 findings의 종결과 출처 인용, 선택 시나리오의
`step_coverage`와 정상·경계·정보 부족 테스트가 없으면 `RESEARCH_INCOMPLETE`로 거절한다.
2차 fragment가 있으면 판정 변경마다 `second_pass.revisions` 기록을 요구한다.
`step_coverage`에서 제외한 단계가 있으면 부분 범위 계약으로 기록되고, 최종 결과는
최대 `partially_reproduced`다.

`agent-harness-init`은 Builder 실행 전에 claim별 evaluator plan과 테스트를 동결한다.
plan에 gap이 있으면 해당 claim은 `RESEARCH_INCOMPLETE`로 등록되어 Agent 쌍을 시작할
수 없다. `agent-bundle-prepare --supplement`로 gap을 닫으면 `PENDING`으로 돌아간다.
공개 실행 정보는 `claims/<claim-id>/runtime-contract-NNN.json`에 revision별로 남긴다.
Sol/Terra는 가장 높은 revision의 실행 방식·공개 예제·공개 자산을 읽는다. 보완 후에도
원래 claim과 Builder context는 덮어쓰지 않고 봉인 테스트는 전달하지 않는다.
평가 데이터가 부족하면 그 사실을 기록하고 `reproduced`를 허용하지 않는다.
원래 입력·기대값을 유지하면서 보완할 경우 다음 명령을 사용한다.

```text
replica-mvp agent-bundle-prepare REGISTRY CLAIM_ID --supplement SUPPLEMENT_JSON
```

보완 JSON은 위 `evaluation` 필드만 사용한다. 기존 case에는 검사를 추가하고,
`additional_cases`에 새 사례를 넣는다. 기존 입력·기대값·검사·정책은 교체하지 않는다.
기존 plan을 덮어쓰지 않고 새 revision을 남긴다. 봉인 평가 제출 후에는 보완할 수 없으며,
계약을 바꿔야 하면 새 실험을 준비한다. 구현 후 준비한 plan은 `prepared_before_implementation: false`로
남기며, 그 평가만으로 구현 전 봉인 조건을 충족했다고 판단하지 않는다.

개발 루프의 성공 후 `agent-candidate-finalize`가 manifest와 파일을 결속하고 최종
평가까지 자동으로 실행한다. 하네스에 지정된 Codex/Claude CLI를 별도 평가 프로세스로
호출하므로 기본 경로에 별도 Judge 스크립트는 필요하지 않다. 이 평가기의 독립성 표시는
`same_session`이며, 실제 CLI 사용 이벤트에서 확인된 토큰을 측정값으로 기록한다.

평가를 별도 시점에 실행하려면 `--bind-only`로 `IMPLEMENTATION_READY`에 남긴 뒤
`agent-bundle-evaluate REGISTRY CLAIM_ID`를 호출한다. 새 하네스는 이 중간 상태에서
`agent-harness-finish`로 종료할 수 없다. 별도로 준비한 평가기를 사용할 때만 다음 옵션을 준다.

```text
replica-mvp agent-bundle-evaluate REGISTRY CLAIM_ID \
  --judge-command '["python3", "/absolute/path/to/evaluator.py"]' \
  --judge-identity evaluator-name --judge-mode same_session
```

Judge command는 생성기가 아니라 평가기다. JSON 요청을 stdin으로 받아 `{pass, reason}`을
stdout으로 반환한다. 전달된 `timeout_seconds`를 지킨다. 품질 요청은 원입력·기준·reference와
두 반복 출력을 포함하며, 구현 검토 요청은 실행한 소스·manifest·입출력을 포함한다.
완전한 독립성을 확보하지 못했다면 `same_session`으로 표시한다. Judge가 없거나 오류가
나면 의미 품질 또는 구현 충실도가 미평가로 남는다. Builder의 개발 테스트를 Judge로
사용하지 않는다.

평가기는 모든 출력을 먼저 생성한 후 채점한다. `contract` 반복 정책은 양쪽 출력에
같은 필수 값·구조·품질 기준을 적용한다. 반드시 결정적이어야 하는 출력은 case 또는
전체 plan에 `repeat_policy: "exact"`를 지정한다. 같은 candidate의 봉인 재제출을 거절하고
scenario당 최대 세 번의 제출 한도를 적용한다. 개발 수정 횟수와 별도다.
각 반복은 새 세션에서 같은 순서의 입력을 실행한다. 반복 내부에서는 상태를 유지한다.
공개 예시는 공개 자산만 넣은 또 다른 세션에서 실행하므로 봉인 자료·대화·캐시를
물려받지 않는다. 자산은 서버가 시작하기 전에 준비한다.

같은 계약 안에서 고칠 수 있는 실패는 `agent-bundle-retry REGISTRY CLAIM_ID`로
기존 Sol/Terra 쌍을 다시 준비한다. 이전 코드·개발 상태·최종 결과는 보존하며, 개발
시작 시점·자원 기록과 전체 평가 예산을 초기화하지 않는다. Sol은 미리 준비된 ACTIVE
상태를 사용해 Terra와 직접 수정 지시를 교환한다. 수정된 후보가 개발 단계를 마치면
다시 최종화한다. 같은 후보는 재제출할 수 없고, 세 번째 제출 이후 재개는 거절한다.
봉인 사례별 정답·실패 이유를 수정 지시로 전달하지 않는다. 조사나 계약 변경이
필요하면 별도 2차 보완 실험으로 넘긴다. 잡힌 실행 중단은 INTERRUPTED로 기록하며
이미 사용한 제출 횟수에서 차감하지 않는다.
개발 시작 시점이 기록되지 않은 구형 실행 상태는 같은 예산으로 재개했다고 검증할 수
없으므로 새 실험을 준비해야 한다. 과거 산출물과 평가 기록은 그대로 남긴다.

실행은 복사된 구현의 임시 디렉터리에서 수행한다. 평가 경로나 정답을 실행 인자로
넘기지 않으며 테스트 결과는 평가 영역에 남긴다. 이 디렉터리 분리는 운영체제 수준의
악성 코드 sandbox가 아니다. 승인된 구현과 의존성을 사용해야 한다.

평가 결과의 위치는 명령 응답의 `public_run_dir`, `vault_dir`로 확인한다.

- 공개 run: 동일한 `implementation/`, `replica.json`, `replica-spec.json`,
  `public-examples.json`, 필요한 `artifacts/`, `replica-result.json`, `completion-assessment.json`.
- 평가 영역: 동결 tests/lock, 첫 출력·반복 출력, 실제 실행 기록, 파일 해시,
  사례별 결과, 구현 검토와 평가 요약. 공개 예시의 파일만 공개 run으로 복사한다.

구현·평가·출력·자산 해시를 결속하며 실패한 실행도 부분 코드와 기술 판정을 보존한다.
기술 판정과 별개인 투자 판단 보고서와 회사 전체 미평가 claim 보고는 이번에 변경하지 않는다.

공개 번들에 새로운 JSON 입력을 주려면 기존 명령을 사용한다.

```text
replica-mvp run-replica PUBLIC_RUN_DIR --use-model-adapter < new-input.json
```

외부 의존성이 없는 번들은 옵션 없이 실행한다. 파일 출력은 새 출력 디렉터리에 보존하고
반환 JSON에 실제 절대 경로를 담는다. 새 입력 파일은 `--input-assets ASSET_MAP.json`으로
넣는다. 예를 들어 `{"inputs/new.pdf":"/absolute/path/new.pdf"}`는 실행 디렉터리의
`inputs/new.pdf`에 파일을 준비한다. 원래 공개 자산을 같은 이름으로 바꿀 수 있지만
구현 파일을 덮어쓸 수는 없다. 입력 JSON에는 계약에 맞는 새 상대 경로를 지정한다.

`--session`을 추가하면 stdin의 JSON 객체 배열을 같은 세션에 순서대로 전달하고
출력 배열을 반환한다. 새 질문을 이어 묻는 대화나 상태 변화 검사에 사용한다.
계속 켜 둔 서버가 필요한 경우 공개 manifest의
command를 implementation 디렉터리에서 실행한다. 필요한 환경변수와 원래의 의존성이
준비돼 있어야 하며, 공개할 수 없었던 입력 자산은 별도로 준비해야 한다.
설치된 Python 패키지와 CLI 버전은 별도로 관측해 선언된 버전과 함께 남긴다.
관측할 수 없는 모델·자원 revision은 미확인으로 표시하며, 확인된 버전 불일치는
완전 재현 조건을 통과하지 못한다. 버전을 자동으로 교체하지 않는다.

## 자원 기록과 조기 종료

개발 예산은 2차의 `handoff.experiment_budget`, 최종 평가 예산은 `evaluation.budget`이다.
미지정 개발 예산은 null로 명시하며, 최종 평가의 기본값은 요청당 120초·전체 600초다.
Sol은 각 작업 전에 `agent-execution-check EXECUTION_STATE`로 남은 예산을 확인하고
허용된 시간 이하의 명령 제한을 Terra에 지시한다. 실행 도중의 제한은 Sol/Terra가
적용하며, 개발 판정도 누적 자원과 시간을 검사한다. 최종 평가 runner는 시작·요청·Judge에
남은 예산을 적용하고 HTTP의 느린 응답에도 전체 요청 시간을 제한한다. 로컬 HTTP가
다른 주소로 리다이렉트하면 실행 성공으로 취급하지 않는다.

Builder feedback의 `resources`는 기존 시도 기록에 보존된다.

```json
{
  "measurements": [
    {"metric":"economic_cost","phase":"execution","value":null,"unit":"USD",
     "status":"unknown","basis":"CLI usage was not monetarily metered.","recorded_at":"2026-09-07T00:00:00+00:00"}
  ],
  "human_interventions": [{"task":"Prepare permitted input files","seconds":null,"basis":"Duration was not measured."}]
}
```

`measured`, `estimated`, `unknown`을 구분하고 미측정 값은 null로 남긴다. 인시·대기·자료
준비·토큰·경제적 비용을 섞지 않는다. CLI 구독의 추가 청구가 없다는 이유로 실행 비용을
0으로 만들지 않는다. 금액 예산이 있는데 실제 비용을 측정할 수 없으면 예산 준수를
확인할 수 없으므로 실행을 차단한다.

`stop_reason: {category, reason, evidence}`로 접근·자료·환경·예산·조사 부족 등 종료
사유를 전달할 수 있다. 차단 조건과 예산 소진은 3회 수정 이전에도 `FAILED`로 끝난다.
단순 실패 여부만으로 기술 자체가 복제 불가능하다는 뜻을 부여하지 않는다.


## 실행 전 제어 오류 복구

활성화 정보에는 같은 Operator의 `execution_state_path`를 넣는다. Builder는
이 경로를 `agent-execution-check`에 전달해 예산 제어 정보만 확인할 수 있다.
상태 파일 본문이나 Operator·평가 자료를 읽는 권한을 뜻하지 않는다.

제어 오류를 수정한 뒤 `agent-continuity-retry-preflight REGISTRY CLAIM_ID`로
같은 쌍을 한 번 재개할 수 있다. 구현 작업 0회가 실측으로 기록되고 테스트를 실행하지
않았으며 후보 산출물도 없는 환경 오류에만 적용한다. 기존 실패 기록을 보관하고
원래의 시작 시각, 남은 예산, 자원 사용 기록과 평가 기준을 유지한다. 일반 구현 실패나
예산 소진을 이 명령으로 초기화할 수 없다.


개발 성공 뒤 명세에 없는 파일 때문에 번들 결속이 거절된 경우에는
`agent-bundle-retry`로 같은 쌍을 재개할 수 있다. 이 경로는 최대 두 번이며,
선언된 코드와 이전 제어 상태를 보관하고 예산을 유지한다. 봉인 평가가 시작되지
않았으므로 봉인 제출 횟수와 구분한다. 수정한 제출물은 개발 검사와 최종 평가를
다시 거쳐야 한다.


번들은 최대 256개 파일, 200MB로 제한한다. 조사에서 선택한 공개 엔진의 실행 파일도
해시·출처·버전·라이선스를 선언해 포함할 수 있다. 명세에 없는 Python 바이트코드
캐시(`__pycache__/*.pyc`)는 검사 대상 원본과 공개 복사본에서 제외한다. 다른 미선언
파일과 심볼릭 링크는 계속 거절한다. 의존성 버전 관찰은 설치 패키지·모델 CLI 외에
번들에 포함한 Dagu, Python 표준 라이브러리 배포 버전과 연결된 SQLite 엔진도 지원한다.


직접 전달 전에 Agent 턴이 잘못 종료된 경우에는 중단을 먼저 기록한다.
`agent-continuity-resume REGISTRY CLAIM_ID`는 같은 쌍을 한 번만 재개하며, 기존
execution-state 파일·수정 번호·완료된 라운드·예산을 그대로 유지한다. 수신자가
직접 피드백을 기다리도록 활성화한 뒤 송신자가 자기 증거를 검증해 직접 전달한다.
부모는 잘못 반환된 의미 내용을 읽거나 중계·저장하지 않는다. 반복 중단, 개발
종료 또는 예산 소진을 이 경로로 초기화할 수 없다.
