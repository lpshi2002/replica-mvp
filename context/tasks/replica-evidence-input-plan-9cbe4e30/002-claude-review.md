# Claude 검토: 001 제안과 P1~P4의 구현 단위

작성: Claude Code, 2026-10-15. 코드 읽기만 했고 테스트·기업 실행은 하지 않았다. 아래 "확인"은 코드에서 본 사실이고, "제안"은 아직 구현되지 않은 안이다.

## 결론

001의 세 묶음 방향과 순서(P1·P2 결함 수정 → P3)에 동의한다. 다만 아래 네 가지는 001에 없어서 구현안에 넣어야 한다.

- **N1:** 무효 근거 ID를 거르는 기준에 관측 ID가 빠져 있다. 지금 기준으로는 정당한 화면 근거도 지워진다.
- **N2:** 업로드 파일 내용은 지금 `plan_sha256`에 묶이지 않는다. 이 공백은 P3의 전제다.
- **P2:** 새 검증 코드는 필요 없다. CLI에 복제된 루프를 `company_features`로 통합하고, 거기서 기존 `_validate_bound_artifact`를 한 번 호출하면 된다.
- **P3:** 새 생성 스키마는 필요 없다. 기존 `replacements`를 업로드 텍스트에도 적용하는 방식이 가장 작다.

## P1. 근거 참조 검증 — 수정해서 수용

**확인한 사실**

- `web_demo.py:784`는 판정의 `evidence_event_ids`에서 무효 ID를 지운다. 그 뒤에도 `status`는 그대로 둔다. 그래서 근거 ID가 전부 가짜인 `passed`도 성공으로 남는다.
- 허용 집합은 `record["events"]`의 ID뿐이다.
- 관측 ID는 행동 수+1로 붙는다(`:517`, `:562`). 계획 중단 직전의 화면처럼, 대응하는 사건(event) 없이 생기는 관측 ID가 있다. 사건이 하나도 없으면 마지막 화면의 ID가 `{cid}-start`가 된다(`:705`).
- 판정기가 받는 `screen_evidence`는 이 관측 ID로 표시된다. 따라서 지금 필터는 판정기가 보라고 받은 화면 근거를 지운다(N1).

**제안(`_evaluate_case`만 수정)**

1. 유효 참조 = 사건 ID ∪ 관측 ID.
2. `JUDGE_SCHEMA`에 필수 필드 `evidence_files: string[]`을 추가한다. 유효 값은 `record["file_changes"]`의 path로 한정한다. 파일 변화는 사건 단위로 귀속되지 않으므로, 사건 ID로 파일 근거를 대신 가리키게 하면 추측이 된다. 결과 필드 이름 `evidence_event_ids`는 호환성을 위해 유지한다.
3. 판정기가 `passed`/`failed`를 냈는데 유효한 사건·관측·파일 참조가 하나도 없으면 결과를 `not_evaluated`로 바꾼다. 사유는 "판정이 기록된 근거를 인용하지 않음"으로 남긴다. 실패에도 같은 규칙을 적용한다. 근거 없는 실패도 근거 없는 성공처럼 신뢰할 수 없기 때문이다.
4. 버린 참조는 `rejected_evidence`에 남기고, 판정기의 원래 상태는 `judge_status`에 남긴다. 지운 사실을 결과에서 감추지 않기 위해서다.
5. 결정적 검사는 판정기 참조 규칙의 대상이 아니다. `_deterministic`이 일치한 경로 `matched_paths`를 추가로 반환하게만 한다.
   - 근거 보존은 이미 되어 있다. 작업 공간은 `cases/<cid>/workspace`에 남는다. `write_checkpoint`의 `evidence_sha256`가 `cases/` 전체를 해시한다. `tree_before/after`와 `final_page`도 보존된다. 새 보존 장치는 필요 없다.
   - 초기 화면이나 파일 검사만으로 나온 결정적 `passed`는 그대로 둔다.

**호환성**

- `web_demo.py`가 바뀌면 `evaluator_version`이 바뀐다. 그래서 기존 체크포인트의 판정은 재사용되지 않고 새로 관측된다. 이것은 기존 정책이다.
- 이미 저장된 결과는 다시 쓰지 않는다. `validate_web_result`는 저장된 상태에서 `web_reproduction_status`를 다시 계산하므로 기존 결과는 그대로 검증을 통과한다.
- 참조가 존재한다는 것과 그 참조가 의미상 맞다는 것은 다르다. 이번 변경은 존재만 검사한다고 결과 문서에 적는다.

**부정 사례 테스트(`tests/test_web_demo.py`)**

| 경우 | 기대 결과 |
|---|---|
| 가짜 ID만 낸 `passed` | `not_evaluated`, `rejected_evidence` 기록 |
| 유효 ID와 가짜 ID가 섞인 `passed` | `passed` 유지, 가짜 ID 분리 |
| 사건 0개에서 `{cid}-start`만 인용 | `passed` 유지 |
| 사건 없는 계획 중단 관측 ID 인용 | `passed` 유지 |
| 참조 없는 `failed` | `not_evaluated` |
| `file_changes`에 없는 파일 경로 인용 | 그 경로 거부 |
| 결정적 검사 | 상태 변화 없음 |

## P2. 제공 버전 확인 — 수용, 위치를 좁힘

**확인한 사실**

- `cli.py:546-558`의 루프는 `company_app.company_features`와 같은 일을 한다. 차이는 반환 형식이 튜플 목록이라는 것뿐이다.
- 두 루프 모두 묶인 `candidate_sha256`과 현재 manifest를 대조하지 않는다.
- `copy_bundle`은 파일들을 manifest와 대조한다. `_open_workspace`는 상태 디렉터리의 marker를 manifest와 대조한다. 하지만 manifest 자체는 묶인 해시와 대조하지 않는다.
- 그래서 상태 디렉터리를 새로 만들면, 파일과 manifest를 함께 바꾼 구현도 그대로 제공된다.
- finish 경로는 `_validate_final_result`에서 이미 검증한 뒤 `check_company_app`을 부른다. 그러나 serve-company에는 이 검증이 없다.

**제안**

1. `_serve_company`의 루프를 지우고 `company_features(registry, root, state)`를 쓴다. 제외 목록은 기존처럼 출력한다.
2. `company_features`에서 manifest를 읽기 전에 아래 호출을 한다. 실패하면 그 기능만 `excluded`에 넣는다. 사유는 "구현이 묶인 뒤 바뀜"이다. 나머지 기능은 계속 제공한다.
   ```python
   _validate_bound_artifact(root, {"path": bound["candidate_path"], "sha256": bound["candidate_sha256"]}, label="company feature")
   ```
   - 해시 대조가 상태 디렉터리보다 먼저 일어나므로 새 상태 디렉터리로 우회할 수 없다.
   - 파일 내용은 기존 `copy_bundle`/`_open_workspace`가 manifest와 대조하므로, 둘을 합치면 내용 전체가 묶인다.
3. import는 함수 안의 지연 import로 한다(`from .agent_harness import _validate_bound_artifact`).
   - `agent_harness`는 이미 `company_app`을 지연 import한다. 상단 import를 추가하면 가벼운 `company_app`이 2,000줄짜리 모듈과 그 의존성을 끌어온다.
   - `single_agent`도 같은 private 함수를 이미 재사용한다.
4. 전체 `_validate_implementation_result`는 부르지 않는다. 실행 상태와 영수증 검증은 finish의 책임이다. serve에 필요한 것은 제공하는 내용이 묶인 내용과 같다는 것뿐이다.
5. 평가 표시는 기존 `summary` 필드를 쓴다(`_menu`가 이미 표시함).
   - `final_result.candidate_sha256`이 묶인 해시와 같을 때만 `reproduction_status`를 표시한다.
   - 그 외에는 "미평가"로 표시한다.
   - 상태로 거르지 않는다. 부분 재현이나 미평가 구현도 제공한다.
   - `check_company_app`도 같은 함수를 쓰므로 finish 결과의 `excluded`에 같은 사유가 남는다.

**테스트(`tests/test_company_app.py`)**

- 묶인 뒤 manifest와 파일을 일관되게 바꾸고 새 상태 디렉터리로 실행하면, 그 기능만 제외되고 다른 기능은 제공된다.
- `final_result`가 없으면 "미평가"로 표시된다.
- `final_result`의 후보 해시가 다르면 "미평가"로 표시된다.

**변경하지 않는 것:** 상태 분리, marker 정책, 셸 구조. 기존 marker가 불일치할 때 전체 serve가 실패하는 동작도 이번 범위 밖이다.

## P3. 업로드 변형 — 범위를 좁혀 수용

**확인한 사실**

- `freeze_demo_plan`은 업로드 파일을 복사한다. 그러나 `plan.json`에는 경로만 있다.
- `plan_sha256`은 `plan.json`만 해시한다. 그래서 고정한 뒤 업로드 내용이 바뀌어도 탐지되지 않는다(N2).
- `_instance_case`는 문구만 바꾸고, `_run_case`는 계획 디렉터리의 원본을 그대로 올린다.

**입력 계약(제안)**

1. 새 계획을 고정할 때 `freeze_demo_plan`이 각 업로드에 `sha256`을 기록한다.
   - `validate_demo_plan`은 값이 있으면 대조하고, 없으면 기존(legacy) 계획으로 허용한다. legacy에 해시를 소급해 붙이지 않는다.
   - 결과에는 `upload_binding: hashed|legacy_unhashed`를 남긴다.
2. 변형은 업로드별로 `vary: true`를 선언했을 때만 한다. 이 선언은 구현 전에 고정된다.
   - 선언하지 않은 업로드를 실행 때 바꾸면, 고정된 변형 규칙을 사후에 넓히는 것이 된다.
   - legacy 계획에는 이 선언이 없으므로 동작이 바뀌지 않는다.
3. 첫 지원 범위는 UTF-8 `.txt`/`.csv`, 20KB 이하다.
   - `_instance_prompt`에 해당 파일의 텍스트를 넣는다.
   - 생성기는 기존 `replacements`로 값을 바꾼다. `INSTANCE_SCHEMA`는 바꾸지 않는다.
   - 같은 `swap`을 질문·사실·기대 문구·검사 텍스트·파일에 적용하므로, 다섯 곳의 값이 기계적으로 일치한다.
4. 실행 때 `run_web_demo`는 `_run_case` 전에 `cases/<cid>/inputs/<path>`에 변형된 파일을 쓴다. `_run_case`에는 업로드의 원본 위치 인자(`upload_root`)만 추가한다.
   - 테스터에게 보이는 파일 이름은 같다.
   - 이 위치는 `cases/` 아래이므로 기존 `evidence_sha256`가 자동으로 해시한다.
   - instance 정보에는 `uploads: [{path, source_sha256, sha256, varied, reason}]`을 남긴다.

**실패와 비지원 처리**

| 경우 | 처리 |
|---|---|
| CSV를 바꾼 뒤 행 수나 열 수가 달라짐(`csv` 모듈로 확인) | `ValueError` → 기존 "instance generation failed" 경로로 블록, `not_evaluated` |
| 비지원 형식, 크기 초과, 바뀐 내용 없음 | 원본으로 실행하고 `varied: false`와 사유를 남김. 입력 요구는 삭제하지 않음 |

비지원·무변경 경우에는 `web_reproduction_status`가 `reproduced` 대신 `partially_reproduced`를 내게 한다. 조건은 "`vary`를 선언했는데 적용하지 못함"으로 둔다. 구현자가 고정 예시 파일에 맞춰 만들었을 가능성을 배제하지 못하기 때문이다. 이 조건은 새 필드에만 걸리므로 기존 결과의 재계산은 변하지 않는다.

**재개와 비교**

- 변형 파일은 "고정 원본 + 저장된 replacements"로 결정적으로 다시 만들 수 있다.
- 재실행할 때와 `input_cases_from`을 쓸 때는 파일을 다시 만들고 기록된 `sha256`과 대조한다. 다르면 오류로 처리하고, 조용히 새로 뽑지 않는다(`load_input_cases`의 기존 원칙).
- 완료된 사례를 재사용할 때는 `copytree`가 `inputs/`까지 복사한다.
- `plan_sha256`이 업로드 해시를 포함하므로 원본이 바뀌면 기존 identity 검사에서 거부된다.

**남은 한계(N3):** 업로드에서 계산되는 파생값(예: 합계)은 문자열 치환으로 맞출 수 없다.
- 첫 범위에서는 계획 작성 지침에서 파생값을 리터럴로 쓰지 않게 한다(예: "업로드 행의 합과 같다").
- 판정기는 업로드 내용을 보지 못한다(N4). 이것은 기존 고정 업로드에도 있던 한계다.
- 재검토 조건: 파생값이 필요한 사례가 실제 계획에 나오면, 생성기가 검사값을 계산해 내는 방식을 별도로 검토한다.

## P4. 순서와 완료 기준

| 단위 | 바꿀 곳 | 완료 기준 |
|---|---|---|
| 1 | `web_demo._evaluate_case`, `JUDGE_SCHEMA`, `_judge_prompt`(파일 경로 인용 안내), `_deterministic` | P1 표의 부정 사례 통과. 기존 `test_web_demo`/`test_web_evaluation` 통과 |
| 2 | `company_app.company_features`, `cli._serve_company` | P2 테스트 통과. `check_company_app` 기존 테스트 통과 |
| 3a | `freeze_demo_plan`/`validate_demo_plan`의 업로드 해시 | 새 계획에는 해시 포함, legacy 계획 허용, 원본 변조 거부 |
| 3b | `vary` 선언, `_instance_prompt`/`_instance_case`의 파일 적용, `run_web_demo`의 생성·기록, `_run_case`의 `upload_root` | CSV 변형 후 질문·파일·검사값 일치. 재개·비교 때 해시 재현. 비지원·무변경은 `partially_reproduced`. CSV 구조 깨짐은 블록 |
| 3c | `skills/replica-research/SKILL.md`의 `vary` 작성 지침 | 문서만 변경 |

각 단위가 끝나면 전체 테스트 묶음과 `git diff --check`를 돌린다.

**변경하지 않는 것:** 기업 앱 셸, 테스터 루프, 비용 집계, 개발 로그, `excluded_parts` 처리, 보고서·질문 생성. Delphi 실행 결과도 다시 실행하거나 바꾸지 않는다.

## 001에 대한 이견

- 001의 "유효 근거가 없으면 미평가"에는 동의한다. 다만 N1을 고치지 않으면 정당한 결과까지 미평가가 되는 회귀가 생긴다.
- 001의 "지원 문서/CSV 하나부터"는 새 생성 스키마 없이 `replacements`를 재사용하는 방식으로 좁히자고 제안한다.
- `vary`를 선언했지만 적용하지 못한 경우를 `partially_reproduced`로 낮추는 것은 정책 선택이다. 사용자 확인 대상으로 남긴다.
