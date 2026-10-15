# Replica MVP 현재 구조

2026-09-26, `codex/sol-terra-implementation-bundle`의 `fece800` 위 **미커밋 수정까지 포함한 작업 트리**를 읽어 작성했다. 실제 서비스 배포도나 새 회사 실행 결과가 아니라 현재 코드·Skill의 구조를 설명한다.

- **[통합 HTML — 아키텍처·워크플로 탭](overview.html)**: 두 다이어그램을 내장한 단일 파일. 이 파일만 옮겨도 오프라인으로 열 수 있다.
- [전체 아키텍처](architecture.html): 실행 주체, Python CLI, 구현 Agent, 봉인 평가, 파일 저장소, 사용자 체험의 연결.
- [전체 워크플로](workflow.html): 기업 입력부터 조사·병렬 구현·평가·회사 집계·체험까지, 미실행과 재제출 분기 포함.
- [JSON 원본 — 아키텍처](architecture.json) / [워크플로](workflow.json).
- [검증 및 전달 기록](handoff.json): 원본·HTML SHA-256과 바이트 수, 자동 검사와 시각 검토 결과.

HTML은 단독 파일이며 확대·이동, 검색, 테마 전환, 내보내기를 제공한다. 설명은 한국어이고 Archify의 고정 Viewer UI와 `html lang`은 영어로 남는다.

통합 HTML의 바깥 메뉴는 한국어이며 각 내부 Viewer는 원본 HTML을 그대로 사용한다. 원본을 갱신한 뒤 `python3 build-overview.py`로 다시 묶을 수 있다. 원본의 Archify 검증 기록과 통합 화면의 [별도 브라우저 검증 기록](overview.browser-check.json)은 구분한다.

## 핵심 구조

실제 조사와 Agent 생성·메시지 전달은 열린 Codex·Claude 세션의 도구가 담당한다. Skill은 그 세션이 따를 조사·조율 절차다. 저장소의 Python CLI는 계약 검증, 파일·해시 결속, Agent 신원과 상태 전이, 번들 실행·평가 및 산출물 생성을 담당한다. 독립적으로 기업명을 받아 모든 조사를 수행하는 서버·크롤러로 구현된 구조는 아니다.

Codex의 기본 구현 구성은 전용 Replica Agent 아래 기능별 sibling 쌍이다. Operator는 `gpt-6-astra`·`medium`, Builder는 `gpt-5.6-terra`·`high`를 요청한다. 모든 선택 기능의 쌍을 준비한 뒤 동시에 활성화한다. Replica Agent는 registry의 단일 작성자이며, Operator와 Builder 사이의 의미 있는 지시·피드백을 중계하지 않는다. Claude 경로의 모델·도구 정책은 해당 런타임 Skill을 따른다.

`evaluator-vault/`의 테스트·기대값·참조 근거는 공개 구현 계약과 분리된다. 별도 실행 프로세스에서 같은 해시의 번들을 검사하지만, 기본 Judge의 독립성 표시는 `same_session`이다. 디렉터리 분리가 운영체제 수준의 악성 코드 격리를 의미하지는 않는다.

## 코드와 다이어그램의 대응

| 다이어그램 영역 | 확인한 구현·계약 |
|---|---|
| 세션 라우팅·조사 | `AGENTS.md`, `CLAUDE.md`, `skills/replica-research/SKILL.md` |
| 1차 확정 | `project.py:743` — `finalize_first_pass`: 5개 범위 체크포인트, 후보·보류 항목의 처리와 근거 검증 |
| 2차 입장 조건 | `second_pass.py:538` — `_research_agent_claims`: 준비도·인계·fragment 식별자·워크플로 대응·요약 검사 |
| CLI·공개/봉인 계약 | `cli.py:444`, `agent_harness.py:172` — `prepare_agent_harness`: claim별 작업 영역·공개 계약·봉인 원본·registry 생성 |
| 기능별 Agent 쌍 | `.agents/skills/orchestrate-replica-agents/SKILL.md`, `.agents/skills/run-replica-agent-protocol/SKILL.md` |
| 직접 통신·개발 수정 | `agent_protocol.py`, `agent_execution.py:403` — 메시지·동료 신원·nonce·수정 순서·예산 검증 |
| 평가 계획 동결·최종화 | `bundle_evaluation.py:174`, `agent_harness.py:1123`, `cli.py:420` — 준비된 계획과 후보 결속 후 별도 평가 |
| 실행·Judge | `bundle_runtime.py:279`, `bundle_runtime.py:117` — `stdio_json` 또는 로컬 `http_json`, 기본 로컬 모델 CLI Judge |
| 판정·실험 기록 | `completion.py:479`, `bundle_evaluation.py:671` — 재현 범위·검사 결과·비용/시간·현재/누적 수정 횟수 |
| 재제출 | `bundle_evaluation.py:988` — 동일 쌍·동결 계약·시작 시점·자원 이력을 유지하고 총 봉인 제출 3회 제한 |
| 회사 전체 결과 | `agent_harness.py:1523`, `agent_harness.py:1662` — 전체 claim과 미실행·개발 중단·최종 판정을 집계 |
| 체험 | `builder.py:256`, `bundle_evaluation.py:1090`, `experience.py:221` — 공개 번들을 새 입력·입력 파일·세션·상태 디렉터리로 실행 |

표의 Python 파일은 `src/replica_mvp/` 아래에 있다. 읽은 파일의 실제 SHA-256은 [source-evidence.json](source-evidence.json)에 남겼다. 미커밋 코드가 대상이므로 Archify의 커밋 고정 저장소 검증 기능을 사용했다고 주장하지 않는다.

## 워크플로 해석

1. 회사명·URL을 받아 1차 공개 조사를 수행하고 근거·중복·제외·보류를 확정한다. 정상적으로 모든 후보가 제외되어 `no_ai_claims`가 되면 회사 결과를 생성하고 종료할 수 있다.
2. 모든 1차 claim을 2차에서 재검증한다. 실행 가능 claim은 전체 워크플로 단계, 구현 방법, 입력·출력, 외부 의존과 평가 기준을 계약으로 만든다. 사용자가 조사만 요청하면 여기서 멈춘다.
3. CLI가 조사와 원본 fragment를 검사한다. `ready`와 `build`를 충족한 기능의 평가 계획을 구현 전에 동결한다. 준비 gap으로 등록된 기능과 미선정 기능은 사유를 보존한다. 필수 계약이 잘못되어 파싱 자체가 거절되는 경우는 정상적인 회사 결과 완료와 다르다.
4. 각 기능의 Operator·Builder 쌍을 준비하고 모두 활성화한다. 초기 구현 이후 개발 수정은 최대 3회다. 생성·환경·접근·예산·프로토콜 문제와 개발 검사 실패를 구분한다.
5. 개발 통과 후보를 최종화하고 봉인 사례·변형 입력·반복·구현 충실도를 평가한다. 같은 계약에서 수정 가능한 실패는 동일 쌍으로 돌아가되 봉인 제출은 최초 제출 포함 최대 3회다. 회사 결과와 공개 번들은 별도로 보존된다.
6. 모든 기능의 판정·미실행 사유·중단 이유·결과 경로를 `company-claims.json`에 모은다. 공개 번들은 `run-replica` 또는 `experience`로 체험한다. `--state-dir`은 번들이 저장한 상태를 유지하며 입력 계약의 대화 이력을 자동 구성하지 않는다.

## 보조 경로와 미구현 범위

- 단일 `replica-second-pass-result/v1`의 JSON 전용 부품은 `prepare-operator`·`finalize-operator`, `codex_operator.py`, `builder.py`를 사용한다. 파일·네트워크 계약은 회사 번들 경로에서 처리한다.
- 수동 run의 `init/build/evaluate/report` 프롬프트 경로는 `project.py`에 호환용으로 남아 있다.
- `reporting.py:371`의 개별 실행 보고서와 `project.py:297`의 기존 보고는 존재한다. 새 번들 경로의 `company-claims.json`을 읽어 회사 전체 서술형 보고서를 생성하는 단계는 아직 없다.
- 범용 원제품 UI는 만들지 않는다. 외부 API·데이터·모델은 회사별 재현 계약과 생성 번들의 의존성이며, 모든 구현이 동일한 외부 서비스를 사용한다고 가정하지 않는다.

## 다이어그램 검증

두 HTML 모두 showcase 9/9 검사, 구성 오류 0·경고 0이다. 각 HTML의 SHA-256에 결속된 실제 Chrome 검사에서 1440×900, 1600×1000, 1920×1080, 2048×1320 모두 가로·세로 넘침이 없었다. 밝은/어두운 테마의 캡처를 별도로 확인했다.

자동 브라우저 검사는 `*.visual-check.json`, 이미지 검토 범위와 결과는 `handoff.json`에 분리했다. 기본 READ 화면의 배치·연결선·텍스트·대형 화면 균형을 시각 검토했으며, 모든 내보내기 형식을 수동 시험한 것은 아니다. 다이어그램 파일만 추가했고 제품 코드와 실행 결과는 변경하지 않았다.
