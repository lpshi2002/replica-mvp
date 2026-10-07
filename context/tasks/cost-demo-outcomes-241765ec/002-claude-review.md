# Claude 검토 — cost-demo-outcomes (001 Codex 제안 대상)

**결론: Codex 제안의 큰 방향(비용 기록·AI의 실제 사례 실행·관측 결과를 한 실행 기록으로 묶기, 기존 자원 형식·파일 효과 검사·전체 주장 집계 재사용)은 수용한다. 다만 비용 계측의 실제 결함 두 가지와 첫 검증 범위의 과대가 빠져 있다.**

1. 기존 판정 토큰 기록은 "일부 수집"보다 나쁘다. 캐시 토큰이 빠진 값이 `measured`로 저장돼 있다(CDO-07).
2. 복제품 내부 모델 호출의 계측 방법이 없다. 후보를 고치지 않는 최소 수단이 있다(CDO-08).
3. 첫 기술 검증에 harness·2차 계약·completion·Skill 변경은 필요하지 않다. 기존 `bundle_session`으로 더 작게 시작할 수 있다(CDO-11, CDO-14).

이 검토는 Codex 제안을 먼저 읽은 뒤 진행했으므로 독립 평가가 아니다. 소스·실행 기록은 읽기만 했다. JSON과 해시를 읽는 읽기 전용 Python 한 줄 명령만 실행했으며 테스트·모델 호출·제품 실행은 하지 않았다.

## 판단 기준 (Codex 기준에 더한 것만)

- **측정값의 의미가 정확한가.** `measured`라는 표시가 붙은 값은 실제로 그 범위를 모두 덮어야 한다. 일부만 잰 값은 미측정과 같은 수준으로 위험하다. 근거: 방향 문서 5절 "미측정은 0이 아니다"([project-direction.md:109](/Users/cho/replica-mvp/context/project-direction.md:109)), brief의 "구독료를 개별 실행의 실측 비용으로 바꾸지 않는다".
- **첫 검증은 가장 작은 변경으로 세 결과를 실제로 낸다.** 운영 규칙은 방향 문서만으로 바꾸지 않는다([project-direction.md:208](/Users/cho/replica-mvp/context/project-direction.md:208)).

## 기존 쟁점 응답

| ID | 판단 | 핵심 근거·보완 |
|---|---|---|
| CDO-01 | **수용(범위 축소 조건부)** | `demo.py` 하나에 계획 검증→실행→관측→판정→결과를 두는 것에 동의한다. 단, 첫 단계에는 harness 연결이 필요 없다(CDO-14). |
| CDO-02 | **수용 + 보완** | 인용은 코드와 맞다. `bind_single_implementation`의 `unknown_resources`([single_agent.py:121](/Users/cho/replica-mvp/src/replica_mvp/single_agent.py:121)), 금액 상한 시 실행 차단([bundle_evaluation.py:529](/Users/cho/replica-mvp/src/replica_mvp/bundle_evaluation.py:529)), Builder 자기보고 자원의 저장([agent_execution.py:455](/Users/cho/replica-mvp/src/replica_mvp/agent_execution.py:455))을 확인했다. 보완할 점: Builder 피드백의 `status: measured`는 영수증 없이 AI가 쓴 값일 수 있다. 출처를 `self_reported`로 구분해야 한다. 판정 계측의 결함(CDO-07), 중첩 호출(CDO-08), 과거 영수증(CDO-09), 중복 집계(CDO-10)를 새로 제기한다. |
| CDO-03 | **수용(조작 경계는 수정 제안)** | 공개 예시는 고정 재생이고 판정자는 후보를 실행하지 않는다는 분석에 동의한다. 결정적 검사를 유지하는 것도 맞다. 다만 첫 단계에서 `play.py` 지속 프로세스를 AI가 조작하게 하는 것은 새 구현 부담이 크다. 대안은 CDO-11. |
| CDO-04 | **수용 + 단순화** | `run_published_bundle`이 `replica-result.json`을 요구한다는 점을 확인했다([bundle_evaluation.py:1113](/Users/cho/replica-mvp/src/replica_mvp/bundle_evaluation.py:1113)). 그러나 `bundle_session`은 manifest만 요구한다([bundle_runtime.py:290](/Users/cho/replica-mvp/src/replica_mvp/bundle_runtime.py:290) 부근). 따라서 첫 시연에는 `public_demo` harness 분기가 필요 없다. 운영 경로 분기는 첫 검증 뒤로 미룬다(CDO-14). |
| CDO-05 | **수용 + 범위 확대** | `_judge`가 `NOT_EVALUATED`를 반환해도 사례 `pass`는 거짓이 된다는 지적은 맞다([bundle_evaluation.py:637](/Users/cho/replica-mvp/src/replica_mvp/bundle_evaluation.py:637)). 변환은 completion에서 끝나지 않는다. 결과의 `failure_category`가 `quality_gap`으로 채워지고([bundle_evaluation.py:968](/Users/cho/replica-mvp/src/replica_mvp/bundle_evaluation.py:968)), 구현 검토 미평가도 "did not pass" 공백이 된다([completion.py:500](/Users/cho/replica-mvp/src/replica_mvp/completion.py:500)). 그 뒤 claim은 `RESULT_FAILED`가 된다([bundle_evaluation.py:984](/Users/cho/replica-mvp/src/replica_mvp/bundle_evaluation.py:984)). **최소 수정:** 새 경로는 `assess_bundle_execution`을 재사용하지 않고 `demo.py` 안에서 두 축(실행/조건 판단)을 계산한다. 첫 단계에서 `completion.py`·`_judge`를 바꾸지 않아 기존 봉인 결과의 해석을 보존한다. Codex 구현표 4단계의 `completion.py` 변경은 철회를 권한다. |
| CDO-06 | **수용 + 1건 보완** | `retrospective` 표시, 사람 검토 `pending`, 판정자 분리를 독립으로 부르지 않는 점([cli.py:446](/Users/cho/replica-mvp/src/replica_mvp/cli.py:446))에 동의한다. 보완할 점: Delphi 세션 README의 데모 대본은 세션 버전을 만든 에이전트가 직접 썼다([demo-session/README.md](/Users/cho/replica-mvp/work/delphi-ai-v2/demo-session/README.md), `orchestration/actions-result.json`의 result 본문). 이 대본을 시연 계획으로 쓰면 사례 설계자가 구현자다. 계획에 `case_author`를 두고, 사례는 공개 조사 근거와 `public-examples.json`에서 우선 도출한다. |

## 새 쟁점

### CDO-07 — 기존 판정 토큰은 캐시 토큰이 빠진 채 `measured`로 기록된다

- **확인한 사실:** Claude 판정은 `usage`에서 `input_tokens`, `output_tokens`, `cached_input_tokens`만 남긴다([bundle_runtime.py:174](/Users/cho/replica-mvp/src/replica_mvp/bundle_runtime.py:174), [bundle_runtime.py:184](/Users/cho/replica-mvp/src/replica_mvp/bundle_runtime.py:184)). Claude CLI의 이름은 `cache_read_input_tokens`·`cache_creation_input_tokens`이므로 캐시 토큰이 모두 빠진다. 보존된 Claude CLI 영수증을 보면 `input_tokens` 48 대 `cache_read_input_tokens` 1,400,785였다(`work/delphi-ai-v2/demo-session/orchestration/chat-result.json`). 실제 Delphi run-2 결과도 판정 호출마다 `input_tokens`가 2~4이며 `measured`로 저장돼 있다(`claude-opus-medium-run-2/final-results/runs/claim-00{1,2,3}/attempt-001-*/replica-result.json`의 `resources`).
- **추가로 확인한 누락:** 판정 CLI가 0이 아닌 코드로 끝나면 `_run_command`가 stdout을 버리고 예외를 낸다([bundle_runtime.py:108](/Users/cho/replica-mvp/src/replica_mvp/bundle_runtime.py:108)). 따라서 실패·시간초과 호출의 사용량은 사라진다. CLI는 `--model` 없이 호출되며([cli.py:449](/Users/cho/replica-mvp/src/replica_mvp/cli.py:449)), 기록에는 `claude-cli-final-evaluator`라는 이름만 남는다. 실제 판정 모델은 기록되지 않는다.
- **영향:** "판정 토큰은 실측"이라고 보고하면 입력 토큰이 수백 배 과소 표시된다. `unmeasured`에도 이 공백이 나타나지 않는다. 코드 확인 결과 Codex 제안의 "일부 토큰 사용량을 수집한다"는 표현은 이 정도의 과소 측정을 드러내지 못한다.
- **최소 수정:** CLI 호출과 영수증 저장을 한 helper로 묶는다. 이 helper가 기존 판정과 새 테스터·판정을 함께 담당한다.
  - 원본 envelope 파일을 보존한다.
  - 모든 usage 키와 `modelUsage`의 관측 모델을 기록한다.
  - 실패한 호출도 시도로 남긴다.
  - 기존 결과 파일은 다시 쓰지 않는다. 보고서가 과거 기록을 인용할 때만 "캐시 토큰 제외·판정 모델 미기록"을 표시한다.

### CDO-08 — 복제품 내부 모델 호출은 실행기 쪽 PATH shim으로 계측할 수 있다

- **확인한 사실:** 세 엔진 모두 `shutil.which("claude")`로 CLI를 먼저 찾는다(`actions/engine/delphi_actions.py`는 `claude` 직접 호출, `interview/engine/interview.py:67`, `chat/engine/main.py:31`). `bundle_environment`는 실행기의 `PATH`를 그대로 넘긴다([bundle_runtime.py:33](/Users/cho/replica-mvp/src/replica_mvp/bundle_runtime.py:33)). Actions 엔진은 호출마다 최대 2회를 시도하고(`delphi_actions.py:59`), 이벤트마다 자동화를 최대 6개까지 병렬로 검사한다(`delphi_actions.py:958`).
- **영향:** Codex의 "별도 기록하거나 미측정" 표현에는 수단이 없다. 이대로면 시연 비용의 가장 큰 부분인 복제품 실행이 계속 `unknown`으로 남는다.
- **최소 수정 (제안, 미검증):** 실행기가 임시 디렉터리에 `claude` 래퍼를 만들어 `PATH` 앞에 둔다. 래퍼는 실제 CLI를 그대로 실행하면서 각 호출의 envelope·종료코드·시각을 영수증 로그에 남긴다. 이 방식에는 세 가지 장점이 있다.
  - 후보 해시가 바뀌지 않는다.
  - 엔진의 내부 재시도와 병렬 호출이 호출 단위로 보인다.
  - 관측 모델도 함께 얻는다.
- **한계:** `PATH` 밖의 대체 경로(`~/.local/bin/claude`)나 직접 HTTP 호출은 잡히지 않는다. 계측 범위를 `coverage: path_resolved_claude_cli`로 명시해야 한다. 래퍼가 stdout·종료코드를 바꾸지 않는지는 실행으로 검증해야 한다.

### CDO-09 — 과거 제작 영수증은 있으나 정가 환산 추정치이며 일부 구간만 덮는다

- **확인한 사실:** 세션 버전 제작 영수증 3개가 있다(`demo-session/orchestration/{chat,interview,actions}-result.json`). 여기에는 `total_cost_usd`(약 1.48 / 0.99 / 1.55)와 `modelUsage.*.costBasis: "list"`, `duration_ms`, `num_turns`가 있다.
- **해석:** 이 영수증은 정가 기준 환산액이며, 구독 사용에서 실제 청구된 금액이 아니다. 덮는 범위는 세션 전환 작업뿐이다. 원래 run-2 구현의 제작 자원은 모두 `unknown`이다(run-2 결과의 `development_attempts`).
- **영향:** 이 금액을 `economic_cost measured`나 "이번 시연 비용"으로 쓰면 brief의 금지 사항 두 가지를 동시에 어긴다.
- **최소 수정:** 이 값은 `phase: session_conversion`, `status: estimated`, 근거 `CLI list-price costUSD`, 기록 일시로 별도 표시한다. 대상 후보 해시에 연결하고 새 시연 합계와 더하지 않는다. `budget_stop`은 `measured`만 인정하므로([resources.py:115](/Users/cho/replica-mvp/src/replica_mvp/resources.py:115)) 구독 환경에서 금액 상한은 늘 `budget_unverifiable`이 된다. 첫 버전의 실제 예산 수단은 시간·호출 수·사례당 행동 수 상한이다.

### CDO-10 — 결과 파일을 단순 합산하면 제작 자원과 실행 횟수가 중복된다

- **확인한 사실:** 각 결과의 `development_attempts`는 이전 제출 결과의 개발 기록을 앞에 붙인다([bundle_evaluation.py:903](/Users/cho/replica-mvp/src/replica_mvp/bundle_evaluation.py:903)). 따라서 attempt-002 결과에는 attempt-001의 개발 기록이 다시 들어 있다. 봉인 평가는 모든 사례를 두 번 실행하고([bundle_evaluation.py:531](/Users/cho/replica-mvp/src/replica_mvp/bundle_evaluation.py:531)) 공개 예시를 추가로 실행한다.
- **영향:** 기업 비용을 `final-results/runs/*/replica-result.json`에서 합산하면 제작 자원이 중복된다. 평가 실행 비용은 "사례 한 번 사용 비용"의 약 두 배다.
- **최소 수정:** 기업 집계는 claim별 최신 결과 하나를 쓰거나 `(submission, correction_number)` 키로 중복을 제거한다. 시연 비용은 시연 실행의 `events.jsonl`에서만 계산한다. 보고서에는 봉인 평가의 반복 실행 비용을 시연 비용과 다른 항목으로 둔다.

### CDO-11 — 첫 AI 조작은 엔진 JSON 프로토콜 수준에서 기존 `bundle_session`으로 한다

- **확인한 사실:** Actions 엔진 manifest는 bundle 형식이다(`command`, `files`, `environment_variables: []`, `dependency_level: commercial_api`). 현재 파일 해시도 manifest와 일치했다(읽기 전용 확인). `bundle_session(..., workspace=상태 디렉터리)`는 호출마다 엔진을 새로 실행하면서 상태를 이어간다([bundle_runtime.py:263](/Users/cho/replica-mvp/src/replica_mvp/bundle_runtime.py:263)). `play.py`도 턴마다 같은 방식으로 엔진을 한 번씩 호출한다(`actions/play.py:84` `Session.call`). 반면 `play.py`는 파이프 입력에서 `input()` 프롬프트를 줄바꿈 없이 출력한다(`play.py:23`). 외부 실행기가 이를 조작하려면 프롬프트 감지나 pty 처리를 새로 만들어야 한다.
- **제안:** 첫 기술 검증에서는 AI 테스터가 매 턴 엔진 응답을 보고 다음 JSON 요청을 고른다. 예를 들어 `list_pending`의 `pending_id`를 읽고 대본에 따라 승인·거절을 정하거나, 엔진의 확인 질문에 허용된 사실로 답한다. 실행기는 `bundle_session`으로 실제 호출하고 원시 입출력을 기록한다. 이 경로에는 두 가지 장점이 있다.
  - 고객 작업 단계(지시 등록→이벤트→승인 대기→승인/거절→outbox)를 줄이지 않는다.
  - 지속 프로세스 구현이 필요 없다.
- **보완 필요:** stdio 경로는 성공 시 stderr를 버리고 파싱된 JSON만 돌려준다([bundle_runtime.py:313](/Users/cho/replica-mvp/src/replica_mvp/bundle_runtime.py:313)). 시연 기록에는 원시 stdout·stderr를 남기는 작은 변형이 필요하다.
- **한계 표시:** 이 방식에서 AI는 사람용 화면(`play.py`)을 조작하지 않는다. 보고서에 이 사실을 적는다. `play.py`는 해시만 기록하고 사람 체험 단계에서 검증한다. 화면 수준의 AI 조작은 첫 결과물이 나온 뒤에 필요성을 다시 판단한다.
- **Codex 안과의 차이:** Codex는 CLI 화면 출력 조작을 첫 구현으로 권했다. 이 제안은 같은 "실제 조작" 원칙을 더 작은 경계에서 지킨다. 선택에 따라 결과의 표현만 달라지므로 구현자가 정해도 된다. 다만 어느 쪽인지는 결과에 반드시 표시한다.

### CDO-12 — 시연 계획 작성과 기존 봉인 자료의 경계

- **확인한 사실:** 기존 공개 예시는 봉인 입력과 달라야 한다([bundle_evaluation.py:268](/Users/cho/replica-mvp/src/replica_mvp/bundle_evaluation.py:268)). 세션 엔진은 봉인 평가를 받은 1회 호출 엔진과 규칙이 다르다(결제 매칭 수정, [demo-session/README.md](/Users/cho/replica-mvp/work/delphi-ai-v2/demo-session/README.md) "한계").
- **영향:** 시연 사례를 만드는 사람이나 AI가 `evaluator-vault/`를 읽으면 봉인 사례가 공개 시연으로 새어 나간다. 시연 결과로 run-2의 claim-002 `reproduction_status`(partially_reproduced, 1회 호출 엔진 기준)를 덮으면 다른 후보의 결과가 섞인다.
- **최소 수정:**
  1. 계획 작성 입력에서 `evaluator-vault/`를 제외한다고 계획에 기록한다.
  2. 실행기가 해시 비교로 봉인 입력과의 동일성을 검사한다. 내용은 출력하지 않는다.
  3. `company-claims.json`에서 시연 결과를 기존 결과와 별도 항목으로 둔다. 각 항목에는 후보 해시를 붙인다.

### CDO-13 — 첫 검증 범위에서 운영 경로 변경을 뺀다

- **확인한 사실:** Codex 구현표에는 다음 변경이 들어 있다. 1단계의 "2차 계약 지침", 4단계의 `completion.py`·`reporting.py`·회사 결과 연결, 5단계의 harness 분기·Skill이다. 방향 문서는 운영 규칙을 방향 문서만으로 바꾸지 말라고 한다([project-direction.md:208](/Users/cho/replica-mvp/context/project-direction.md:208)). 봉인 선택 옵션(D3)과 평가 실행 방식도 미확정이다([project-direction.md:203](/Users/cho/replica-mvp/context/project-direction.md:203)).
- **영향:** 첫 결과 전에 운영 경로를 바꾸면 범위가 커진다. 승인되지 않은 정책 변경이 함께 들어간다.
- **최소 수정 (권장 순서):**

| 단계 | 변경 | 완료 기준 |
|---|---|---|
| 1 | CLI 호출 helper와 영수증 (CDO-07) | 실패 호출 포함, 캐시 토큰·관측 모델 기록. 기존 판정 경로의 출력 형식은 그대로 유지 |
| 2 | `demo.py` + 손으로 작성·고정한 Actions `demo-plan.json` 1개 | 계획 해시·`retrospective`·`case_author`·기대 결과 근거 검증 |
| 3 | AI 테스터 루프(CDO-11) + PATH shim(CDO-08) | 승인·거절 두 사례가 여러 턴에 걸쳐 실제 실행됨. outbox 변화/무변화를 관측으로 확인. 엔진 내부 호출 수·재시도가 영수증에 나타남 |
| 4 | 별도 판정 + `demo-result.json`·`report.md` | 미평가가 실패로 바뀌지 않음. 비용 표가 측정/추정/미측정/과거 추정을 구분 |
| 5 | 사용자 확인 후: harness 분기·2차 계약·Skill, Delphi 나머지 두 기능 | 한 기업 결과물 세트의 완료 조건으로 넘어감 |

1~4단계는 기존 봉인 경로 코드를 바꾸지 않는다. 1단계가 바꾸는 것은 판정 사용량 기록의 정확도이며, 판정 기준은 그대로다.

## 경계 확인 (진행자 중점 8개)

| 항목 | 판단 |
|---|---|
| (1) 실제 조작 vs 재생+해설 | Codex는 구분했다. 조작 경계는 CDO-11로 좁힌다 |
| (2) 중복·과거 비용 오인 | Codex 원칙은 맞다. 구체적 위험은 CDO-09·CDO-10에서 새로 제기 |
| (3) judge 계측 과장 | Codex는 "일부"라고 썼다. 다만 그 일부가 캐시 제외로 크게 과소 측정된다는 점이 빠졌다(CDO-07) |
| (4) 결과 확인 가능성 | 해시·이벤트·파일 효과는 충분하다. 원시 stderr 보존(CDO-11), 엔진 내부 재시도(CDO-08) 보완 필요 |
| (5) 미실행·미평가 | CDO-05 보완. 원인 분류(관측/가설/추가 확인)는 Codex 안에 동의 |
| (6) 봉인 경계 | CDO-12 |
| (7) 기능 검증 vs 기업 완료 | Codex가 구분했다. 기업 결과물 세트는 Delphi 세 기능의 결과나 미실행 사유가 있어야 완료된다. 특허·규제·경쟁 사업도 필요하며 이번 토론 범위 밖이다 |
| (8) 불필요한 구조 | CDO-13. 새 승인 절차나 범용 프레임워크는 Codex 안에도 없었다 |

## 남은 쟁점과 다음 확인

- **합의 아님.** CDO-07~13은 Codex의 재검토가 필요하다. 특히 CDO-11(조작 경계)와 CDO-13(구현 순서 축소)이 주요 이견이다.
- **실행으로만 확인 가능한 것:**
  1. PATH shim이 세 엔진의 출력·종료코드를 바꾸지 않는가.
  2. Claude CLI가 실패·시간초과 때도 usage envelope을 남기는가.
  3. JSON 수준 AI 테스터가 `pending_id`처럼 동적인 값을 대본 밖 사실 없이 처리하는가.
  4. 현재 설치된 `claude` 버전이 manifest의 2.1.283과 다를 때 결과 표시가 어떻게 되는가.
- 모델 간 합의는 사용자 승인이 아니다. 첫 기업을 Delphi로 확정하는 것도 여전히 미정이다([project-direction.md:196](/Users/cho/replica-mvp/context/project-direction.md:196)).
