# 2차 계약 개편안 (초안): 사람이 써 보는 복제품

> 상태: 초안. 편집용 문서이며 아직 Skill·코드에 반영하지 않았다.
> 대상: `skills/replica-research/agents/replica-second-pass.md` 5~7절(계약 작성 단계).
> 2차 조사 자체(근거 수집, `workflow.steps`, `findings`)는 바꾸지 않는다.

## 1. 목적

Replica는 Bain식 인수 실사 기능 재현을 따른다. 생성형 AI로 대상 기업의 핵심 기능
시제품을 만들고, 사람이 직접 써 보며 다음을 판단한다.

- 기술 구현 난도와 경쟁사·신규 진입자의 대체 가능성
- 경쟁력의 원천이 코드인지, 데이터·고객 업무 결합인지

따라서 복제품은 **사람이 원본과 같은 방식으로 써 볼 수 있어야** 한다.
사람과 AI가 함께 만드는 것도 정상 경로다. 사람이 얼마나 개입했는지는 오염이 아니라
난도 데이터로 기록한다.

## 2. 현재 문제

2차는 사용 방식을 조사해 두지만, 계약 단계에서 이를 채점용 형태로 바꾼다.

- 모든 계약이 `stdio_json` 형태다. stdin으로 JSON 하나를 받고 stdout으로 JSON 하나를 낸다.
  입력에는 설정·자료·사용자 입력이 한 덩어리로 섞여 있다.
- 상호작용 형태(단발/대화/일괄)를 판단하는 항목이 없다.
- `experience`는 질문-답변 기능에만, 선택 사항으로 붙는다(`interaction.type`은
  `question_answer`만 허용).
- 반면 평가 데이터(최소 3 case, novel, metamorphic 등)는 필수다. 없으면
  `RESEARCH_INCOMPLETE`로 멈춘다.

근거 (`work/delphi-ai-v2/research.json`, 2026-09-26):

| 기능 | 원본 사용 방식 (2차 `workflow.steps`) | 현재 계약 | 사람이 써 볼 수 있나 |
|---|---|---|---|
| 디지털 마인드 대화 | 방문자가 크리에이터의 AI와 채팅 | 설정·자료 전체 JSON → 답변 JSON | 질문형 체험만 있음 |
| 크리에이터 인터뷰 | 질문 → 답변 → 진행률 → 다음 질문 (멀티턴) | 답변 배열을 미리 다 써서 한 번에 입력 | 불가 |
| 상황 인식 액션 | 자연어로 자동화 지시 → 이벤트가 오면 실행하거나 확인 대기 | 지시·연락처·이벤트 JSON 하나 | 불가 |

`work/harvey/research.json`(9개 claim)에는 체험이 하나도 없다. 일부 claim은 입력이
고정 UUID, 벤치마크 task 번들, 모델 자격증명 같은 테스트 fixture로 되어 있다.

## 3. 바꿀 것

### 3.1 상호작용 형태 판단 — 새 필드 `interaction`

scenario마다 사용자가 이 기능을 어떻게 쓰는지 기록한다.

`type`은 **주고받는 틀**이다. 틀 안에 담기는 결과물(요약문, 조항 목록, 수정된 docx,
표)은 기능마다 다르며 `user_output`에 적는다. 테스트의 모양도 이 틀을 따른다(3.4).

```json
"interaction": {
  "type": "single | conversation | batch",
  "origin": "company | ours",
  "sources": [{ "url": "…", "excerpt": "…" }],
  "user_input": "사용자가 매번 넣는 것 (텍스트, 파일 종류)",
  "user_output": "사용자가 받아 보는 것 (텍스트, 파일, 표)",
  "reason": "이 형태로 판단한 이유"
}
```

| type | 언제 | 예 |
|---|---|---|
| `single` | 입력 한 번에 결과 하나. 앞 턴에 의존하지 않음 | 요약, 분류, 추출, 조항 제시, 문서 수정 |
| `conversation` | 시스템이 되묻거나 이전 턴의 상태로 다음 응답이 바뀜 | 인터뷰, 요구사항 수집, 반복 수정 |
| `batch` | 여러 건을 넣어 표나 보고서 하나를 받음 | 문서 여러 개 → 검토 표 |

판단 규칙:

1. **기업이 보여 준 사용 방식을 따른다.** 데모, 도움말, 스크린샷, 고객 사례에서 확인한다.
   이때는 `origin: company`이고 출처 발췌를 남긴다.
2. 자료에 사용 방식이 없으면 `single`을 기본값으로 쓰고 `origin: ours`로 표시한다.
   공식 자료를 다시 열어 확인한 뒤에만 이렇게 한다(`boundaries`의 `undisclosed` 규칙과 같다).
3. `workflow.steps`에 되묻기, 진행 상태, 다음 질문이 있으면 `conversation`이다.
   이런 단계를 한 번 호출로 누르지 않는다.
4. 판단이 갈리면 두 형태를 scenario로 나누지 않는다. 더 단순한 형태를 고르고
   `reason`에 남긴다.

### 3.2 입력을 "준비물"과 "사용자 입력"으로 나눈다

지금 `input`은 설정·자료·사용자 입력이 한 JSON에 섞여 있다. 이를 나눈다.

- `setup`: 써 보기 전에 한 번 준비하는 것. 크리에이터 설정, 지식 자료, 플레이북,
  샘플 문서 등. 공개·합성 자료로 미리 채워서 제공한다.
- `user_input`: 사람이 매번 직접 넣는 것. 질문, 파일 업로드, 답변.

규칙:

- `user_input`은 사람이 입력할 수 있어야 한다. 고정 UUID, 내부 ID, 자격증명,
  테스트 전용 필드는 넣지 않는다.
- 원본이 파일을 받으면 파일로 받는다(docx, pdf 등). JSON 안에 텍스트로 넣지 않는다.

### 3.3 체험을 필수로

- `handoff.action: build`인 claim은 모두 `experience`를 가진다.
- `experience.interaction.type`은 3.1의 세 형태를 허용한다.
- 샘플 입력 2~3개와 `setup` 기본값을 같이 준다. 사람이 아무것도 준비하지 않아도
  바로 실행할 수 있어야 한다.
- 원본과 비교할 수 있는 근거 수준(`direct` / `public` / `claim_only`)은 지금처럼 유지한다.

### 3.4 테스트와 복제 정도

#### 세 층

| 층 | 누가 | 언제 | 역할 |
|---|---|---|---|
| 확인 기준 | 2차 AI가 생성 | 구현 전, 고정 | 복제 정도 측정 |
| 개발 중 확인 | 구현하는 쪽(AI 또는 사람+AI) | 구현 중, 자유 | 만들면서 동작 확인 |
| 최종 판단 | 사람 | 구현 후 | 체험(3.3)으로 직접 써 보고 판단 |

#### 확인 기준 테스트는 2차가 원본 근거로 먼저 만든다

- `acceptance_criteria`와 기본 테스트 3종(normal / boundary / insufficient-information)을
  2차가 `interaction`을 정할 때 같이 생성한다.
- **정답은 원본 기업의 공개 근거로 정한다.** 복제품의 실제 동작을 보고 만들지 않는다.
  복제품에 맞춰 정답을 만들면 항상 통과하므로 복제 정도를 잴 수 없다.
  - 예: "근거가 없으면 설정된 대체 문구로 답한다", "짧은 답변으로는 진행률이 오르지 않는다"
- 구현 전에 만들고, 구현 결과를 본 뒤에 바꾸지 않는다.
- 봉인은 필요 없다. 테스트는 공개해도 된다. 지킬 것은 "먼저 정하고 나중에 바꾸지 않는다" 하나다.

#### 테스트는 사용자 입출력 수준으로 쓰고, 형태별 실행기로 돌린다

- 테스트는 "사용자가 넣는 것 → 사용자가 봐야 하는 것"으로 쓴다. 내부 JSON 필드 이름을
  고정하지 않는다. 필드 이름을 고정하면 복제품이 그 JSON 모양으로만 만들어진다.
- 형태별 공통 실행기 3개가 테스트를 복제품에 넣고 결과를 받는다.

| 형태 | 테스트 모양 | 실행 |
|---|---|---|
| `single` | 입력 하나 → 기대 결과 | case마다 새로 실행 |
| `conversation` | 턴 순서 대본 (사용자 발화 → 기대 응답 → 다음 발화 …) | 한 세션에서 순서대로 실행 |
| `batch` | 입력 여러 건 → 기대 표·보고서 | 한 번에 넣고 결과 확인 |

`conversation`을 입력 하나로 누르지 않는다(인터뷰의 답변 배열 사례).

#### 자동 실행과 판정

- 복제품이 만들어지면 확인 기준 테스트가 자동으로 돈다.
- 형식 확인(필수 항목, 파일 생성, 표 구조)은 코드로 판정한다.
- 내용 확인("요약이 맞나", "맞는 조항인가")은 AI 판정자가 한다.
  판정자 이름과 독립 여부(같은 세션 / 별도)를 기록한다.
  판정자가 없으면 해당 case는 `NOT_EVALUATED`로 남긴다.
- 복제 정도 = 통과한 case + `step_coverage`.
  결과는 `reproduced` / `partially_reproduced` / `not_reproduced` 중 하나다.
  제외한 단계가 있으면 최대 `partially_reproduced`다.

#### case별 결과를 공개한다

- 지금은 봉인 때문에 공개 결과에 `passed`/`total`과 종류별 집계만 남는다
  (`src/replica_mvp/bundle_evaluation.py:949`).
- 바꾼 뒤에는 case마다 입력, 복제품 출력, 통과 여부, 판정 이유를 보여 준다.
  어느 테스트가 왜 실패했는지 사람이 볼 수 있어야 한다.

#### 줄이는 것

- 선택으로 낮춤: 봉인 평가, `novel`/`metamorphic` case, 부수효과 검사.
- 평가 데이터가 부족해도 `RESEARCH_INCOMPLETE`로 멈추지 않는다. 부족한 점을 기록하고 진행한다.

### 3.5 그대로 살리는 것

- `workflow.steps`, `step_coverage`: 제외한 단계와 "고객이 잃는 것"은 경쟁력 원천
  (코드인지, 데이터·고객 업무인지)을 판단하는 근거다.
- scenario 축(`oss_only` / `commercial_api` / `proprietary_data`): 대체 가능성 판단에 쓴다.
- `evidence_level`, `boundaries`, `boundaries_origin`.

## 4. 기존 결과에 적용하면 (추정)

아래는 기존 조사 내용만 보고 재분류한 추정이다. 확정하려면 출처를 확인해야 한다.

| claim | type | setup | user_input |
|---|---|---|---|
| Delphi 디지털 마인드 대화 | `conversation` | 크리에이터 설정, 지식 자료 | 방문자 질문 |
| Delphi 크리에이터 인터뷰 | `conversation` | 시작 주제 | 질문마다 크리에이터 답변 |
| Delphi 상황 인식 액션 | 미정 (5절 참고) | 크리에이터 스타일, 연락처 샘플 | 자동화 지시, 이벤트 |
| Harvey assistant | `single` | 지식 자료(선택) | 질문과 파일 |
| Harvey Word 문서 편집 | `single` | 플레이북 | docx와 수정 지시 |
| Harvey review tables | `batch` | 열 질문 정의 | 문서 여러 개 |

## 5. 결정할 것

- [ ] 형태는 세 개로 충분한가? 이벤트 반응형(상황 인식 액션 같은 것)을 `event`로 따로 둘지,
      "지시는 conversation, 이벤트는 샘플로 주입"으로 처리할지
- [ ] 체험 화면: CLI(`replica-mvp experience`)로 충분한가, 간단한 웹 화면이 필요한가
- [ ] 봉인 평가를 선택 사항으로 남길지, 완전히 뺄지
- [ ] 사람+AI 대화 제작을 공식 구현 경로로 둘지, 두면 사람 개입을 어떻게 기록할지
- [ ] 기존 조사 결과(delphi-ai-v2, harvey 등)를 새 계약으로 재분류할지
- [ ] 내용 판정자: 어떤 모델로 할지, 구현과 분리된 세션으로 돌릴지

## 6. 뒷단 영향 (이번 범위에 넣을지 결정 필요)

- `src/replica_mvp/experience.py`: `interaction.type` 허용값을 확장하고, `conversation`·`batch` 실행을 지원
- `src/replica_mvp/second_pass.py`: `interaction`, `setup`/`user_input` 검증, 필수 `experience` 검사,
  평가 데이터 부족 시 중단하던 규칙 완화
- `src/replica_mvp/bundle_evaluation.py`: case별 결과 공개, 형태별 실행기 3개
  (`single` / `conversation` 대본 / `batch`), 사용자 입출력 수준 테스트를 복제품 입력으로 바꾸는 부분
- `src/replica_mvp/bundle_evaluation.py`, `agent_harness.py`: 봉인 평가를 선택으로 바꾸는 경우
- `src/replica_mvp/resources.py`: `human_interventions`를 실제로 기록
- `AGENTS.md`, `CLAUDE.md`, 각 Skill 문서: 기본 경로 설명 갱신
