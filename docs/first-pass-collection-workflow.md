현재 1차 수집은 **회사 하나를 입력하면 5개 조사 에이전트가 자료를 나눠 보고, 컨트롤러가 결과를 워크플로 단위로 합쳐 `research.json`을 만드는 과정**입니다.

중요한 점은 `replica-mvp` CLI가 자동으로 웹을 조사하는 구조가 아니라는 것입니다. Codex가 [Replica Skill](/Users/cho/replica-mvp/skills/replica-research/SKILL.md)을 읽고 에이전트를 운영하며, CLI는 마지막 검증과 완료 처리를 담당합니다.

## 전체 실행 순서

```text
회사명 또는 URL 입력
        ↓
research.json 빈 템플릿 생성
        ↓
4개 조사 에이전트 병렬 실행
        ↓
조사 중 발견한 제품명·기능명 추가 검색
        ↓
5개 체크포인트 완료
        ↓
컨트롤러가 중복 제거·단계 병합
        ↓
최종 AI 워크플로 주장 목록 작성
        ↓
finalize-pass-1 검증
        ↓
전체 주장을 2차로 전달
```

## 1. 회사 정보를 입력합니다

예를 들어:

```text
회사: FurtherAI
공식 URL: https://www.furtherai.com
```

그러면 다음 위치에 작업 폴더를 만듭니다.

```text
work/furtherai/
├── research.json
└── first_pass/
```

처음의 `research.json`은 회사 정보와 조사 진행 상태만 있는 빈 틀입니다.

## 2. 회사 자료를 5개 범위로 나눠 조사합니다

먼저 네 에이전트를 병렬로 실행합니다.

| 에이전트 | 조사 범위 |
|---|---|
| 공식 자료 | 제품 페이지, 기술 문서, API, 도움말, 데모, GitHub |
| 기술 블로그 | 회사의 기술·엔지니어링 글 전체 |
| 사람·조직 | 인터뷰, 발표, 채용공고, 고객·파트너 자료 |
| 보충 자료 | 논문, 특허, 공시, 신뢰할 수 있는 보도 |

조사 과정에서 `AI Grid`, `Workflow Studio` 같은 제품명과 기능명이 발견되면 다섯 번째 에이전트가 각각을 다시 검색합니다.

```text
discovered_names:
- AI Grid
- Workflow Studio
- Eval Studio
```

## 3. 각 에이전트는 페이지를 하나씩 판정합니다

페이지에서 다음 문장을 발견했다고 가정하겠습니다.

> “Our LLM agent reads submission documents and returns normalized fields.”

에이전트는 두 가지를 확인합니다.

- 실제 작업이 있는가?
  - 제출 문서 → 정규화된 필드
  - 있으므로 A1 통과

- 그 작업을 AI가 한다고 원문에 적혀 있는가?
  - `LLM agent`라고 적혀 있음
  - A2 통과

통과하면 후보 주장으로 저장합니다.

반대로 다음 내용은 탈락 목록에 저장합니다.

| 내용 | 사유 |
|---|---|
| 검토 시간을 30배 단축 | `outcome_metric` |
| 투자 유치·고객·인증 | `non_technical` |
| 문서를 자동 전달하지만 AI 언급 없음 | `no_ai_attribution` |

## 4. 발견 즉시 체크포인트에 저장합니다

각 에이전트는 자기 파일만 수정합니다.

```text
work/furtherai/first_pass/
├── official-surfaces.json
├── engineering-blog.json
├── discovered-names.json
├── people-and-organizations.json
└── supplementary-sources.json
```

체크포인트에는 세 종류의 정보가 들어갑니다.

### 조사 진행 상태

```json
{
  "completed": ["이미 확인한 페이지"],
  "remaining": ["아직 확인할 페이지"],
  "discovered_names": ["AI Grid"]
}
```

에이전트가 중단돼도 `remaining`부터 다시 시작할 수 있습니다.

### 통과한 AI 기능 주장

```json
{
  "claim": "제출 문서를 정규화된 데이터로 변환한다",
  "sources": [
    {
      "url": "https://example.com/product",
      "type": "official_product",
      "excerpt": "Our LLM agent reads submission documents and returns normalized fields."
    }
  ],
  "ai_basis": {
    "mechanism": "제출 문서 → 정규화된 필드",
    "signals": ["LLM agent"],
    "source_index": 1,
    "quote": "Our LLM agent reads submission documents and returns normalized fields."
  },
  "workflow": {
    "input": "브로커 이메일과 첨부 문서",
    "steps": [
      {"step": "첨부 문서 분류", "source_index": 1}
    ],
    "output": "정규화된 submission record"
  },
  "replication_leads": [
    {
      "kind": "output_example",
      "source_index": 1,
      "finding": "출처가 정규화된 출력 필드를 보여준다."
    }
  ]
}
```

### 탈락한 내용

```json
{
  "claim": "검토 시간을 30배 줄인다",
  "url": "https://example.com/customer",
  "reason": "outcome_metric"
}
```

## 5. 통과한 주장에 무엇을 저장하는가

주장마다 다음 정보가 저장됩니다.

### `claim`

회사가 공개적으로 주장한 기능입니다.

```text
보험 제출 문서를 정규화된 보험 데이터로 변환한다.
```

### `sources`

이 주장을 발견한 출처 목록입니다. 한 개여도 배열로 저장합니다.

```json
[
  {
    "url": "https://example.com/product",
    "type": "official_product",
    "excerpt": "Our LLM agent reads submission documents and returns normalized fields."
  }
]
```

### `ai_basis`

왜 AI 기능이라고 판단했는지 저장합니다.

```json
{
  "mechanism": "제출 문서 → 정규화된 필드",
  "signals": ["LLM agent"],
  "source_index": 1,
  "quote": "Our LLM agent reads submission documents..."
}
```

### `workflow`

무엇이 들어오고 무엇이 나오는지 저장합니다.

```json
{
  "input": "브로커 이메일과 첨부 문서",
  "steps": [
    {
      "step": "첨부 문서 분류",
      "source_index": 1
    }
  ],
  "output": "정규화된 submission record"
}
```

출처에 중간 단계가 없으면 `steps: []`입니다.

### `replication_leads`

조사 중 이미 발견한 복제 자료 목록입니다. 없으면 빈 배열로 저장합니다.

```json
[
  {
    "kind": "input_sample",
    "source_index": 1,
    "finding": "공개된 샘플 보험 신청서를 테스트 입력으로 사용할 수 있다."
  }
]
```

여기에 들어갈 수 있는 것은:

- 입력 샘플
- 출력 예시
- 스키마와 파일 형식
- API·SDK
- 공개 구현
- 논문·특허
- 벤치마크와 평가 자료

별도 심층 조사를 하지는 않지만 이미 발견한 자료는 버리지 않습니다.

## 6. 컨트롤러가 다섯 결과를 합칩니다

다섯 에이전트가 끝나면 컨트롤러가 체크포인트를 읽습니다.

예를 들어 다음 세 주장이 발견됐다면:

```text
문서를 분류한다
문서에서 필드를 추출한다
정규화된 submission record를 만든다
```

분류와 추출 결과가 별도로 판매되지 않고 최종 record를 만들기 위한 내부 단계라면 하나로 합칩니다.

```text
브로커 제출물
→ 문서 분류
→ 필드 추출
→ 정규화된 submission record
```

이 과정에서:

- 같은 주장의 출처를 합침
- 중복 제거
- 내부 단계를 `workflow.steps`로 이동
- 흡수한 문구를 `merged_from`에 기록
- A1·A2를 다시 확인
- 가장 직접적인 AI 인용을 선택
- 복제 단서를 합침
- 모든 `source_index`를 새 출처 목록에 맞게 수정

이 병합과 A1·A2 재판정은 Codex 컨트롤러가 문맥을 읽고 수행합니다. Python CLI가 의미를 판단하거나 주장을 자동으로 합치지는 않습니다.

## 7. 최종 `research.json`을 만듭니다

정리된 주장 하나는 다음 형태가 됩니다.

```json
{
  "id": "claim-001",
  "slug": "submission-normalization",
  "first_pass": {
    "claim": "제출 문서를 정규화된 보험 데이터로 변환한다",
    "sources": [
      {
        "url": "https://example.com/product",
        "type": "official_product",
        "excerpt": "Our LLM agent reads submission documents and returns normalized fields."
      }
    ],
    "ai_basis": {
      "mechanism": "제출 문서 → 정규화된 필드",
      "signals": ["LLM agent"],
      "source_index": 1,
      "quote": "Our LLM agent reads submission documents and returns normalized fields."
    },
    "workflow": {
      "input": "브로커 이메일과 첨부 문서",
      "steps": [
        {"step": "첨부 문서 분류", "source_index": 1}
      ],
      "output": "정규화된 submission record"
    },
    "replication_leads": [
      {
        "kind": "output_example",
        "source_index": 1,
        "finding": "출처가 정규화된 출력 필드를 보여준다."
      }
    ],
    "testable_claim": "주어진 제출 문서에서 정규화된 필드를 반환한다",
    "routing": "도메인워크플로독특",
    "merged_from": []
  },
  "second_pass": null
}
```

여기서:

- `testable_claim`: 나중에 테스트할 수 있게 고친 문장
- `routing`: 기능 종류를 표시하는 태그
- `merged_from`: 합쳐진 원래 주장들
- `second_pass: null`: 아직 2차 조사를 하지 않았다는 뜻

## 8. 마지막 검증을 실행합니다

다음 명령을 실행합니다.

```bash
replica-mvp finalize-pass-1 work/furtherai
```

검증기는 다음을 확인합니다.

여기서는 의미를 다시 판단하지 않고, 컨트롤러가 정리한 결과의 출처 연결과 형식을 기계적으로 검사합니다.

- 다섯 체크포인트가 모두 완료됐는가
- 남은 조사 항목이 없는가
- AI 인용이 실제 출처 발췌문에 있는가
- AI 용어가 인용문에 있는가
- 단계와 복제 단서가 올바른 출처를 가리키는가
- 입력과 출력이 작성됐는가
- 체크포인트와 최종 주장에 구식 점수 필드가 남아 있지 않은가

통과하면 다음 상태가 기록됩니다.

```json
{
  "workflow": {
    "status": "pass_1_complete",
    "pass_2": {
      "handoff_count": 12
    }
  },
  "summary": {
    "candidate_count": 12,
    "excluded_count": 35,
    "next_step": "run_pass_2"
  }
}
```

`candidate_count`와 `handoff_count`는 같습니다. 1차에서 선별하지 않기 때문에 정리된 주장 12개가 모두 2차로 넘어갑니다.

## 최종 출력물

1차가 끝나면 남는 것은 두 종류입니다.

### 최종 결과

```text
work/<company>/research.json
```

중복과 단계를 정리한 최종 AI 워크플로 주장 목록입니다. 2차는 이 파일을 입력으로 사용합니다.

### 조사 체크포인트

```text
work/<company>/first_pass/*.json
```

각 에이전트의 조사 범위, 진행 상태, 원시 주장, 탈락 후보가 남습니다.

반대로 1차에서는 아직 다음을 만들지 않습니다.

- 완성된 복제 데이터셋
- 최종 출력 스키마
- 테스트 케이스
- 복제 가능성 판단
- Replica 구현 코드

이것들은 2차에서 `research.json`의 각 주장에 추가됩니다.
