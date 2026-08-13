# Replica MVP 인수인계 안내

이 묶음은 소스 코드만 전달하는 ZIP이 아니라, 현재 조사 결과와 실행 가능한
Replica까지 이어받기 위한 작업본이다.

## 현재 상태

### Delphi AI

- 조사 원본: `work/delphi-ai/research.json`
- 상태: 1차 및 2차 조사 완료
- 주장 3개: Replica 준비 완료 2개, 부분 준비 1개
- Replica 제작용 준비 완료 입력:
  `work/delphi-ai/builder_input/grounded-digital-mind-conversation.json`
- 이미 생성된 공개 Replica:
  `work/delphi-ai/operator-workspace/runs/delphi-ai-grounded-digital-mind/a540dbc8d4e704faa0781b54539ffe88afea1f8a13c6e4f261d6c9dad2dd7b3a/`
- 검증 결과: 고정 테스트 3/3 통과

이 Replica는 공개 근거와 작은 합성 데이터로 검증한 제한적 재현물이다. Delphi의
비공개 모델, 프롬프트, 고객 데이터 또는 원제품 동등성을 의미하지 않는다.

### FurtherAI

- 조사 원본: `work/further-ai/research.json`
- 상태: 1차 조사 진행 중
- 아직 Replica 단계에서 시작할 수 없다. 1차 및 2차 조사를 먼저 완료해야 한다.

## 준비

- Python 3.12 이상
- 이 폴더를 작업공간으로 연 Codex

```powershell
py -3.12 -m pip install -e .
```

Python 3.13만 설치되어 있다면 `py -3.13`을 사용해도 된다.

## 기존 Delphi Replica 바로 실행하기

아래 경로가 실행 가능한 Replica 디렉터리다.

```text
work/delphi-ai/operator-workspace/runs/delphi-ai-grounded-digital-mind/a540dbc8d4e704faa0781b54539ffe88afea1f8a13c6e4f261d6c9dad2dd7b3a
```

JSON 객체를 표준 입력으로 전달한다.

```powershell
$run = "work\delphi-ai\operator-workspace\runs\delphi-ai-grounded-digital-mind\a540dbc8d4e704faa0781b54539ffe88afea1f8a13c6e4f261d6c9dad2dd7b3a"
'{"creator_corpus":[],"style_rules":[],"safety_rules":["Never invent personal facts."],"fallback_text":"I do not have enough source information to answer that.","conversation_history":[],"user_question":"What is the creator''s favorite planet?"}' | replica-mvp run-replica $run
```

## 준비 완료 입력에서 Replica를 새로 만들기

Codex에 다음과 같이 요청한다.

```text
work/delphi-ai/builder_input/grounded-digital-mind-conversation.json을
준비 완료 Second-pass 입력으로 사용해서 Replica를 새로 만들어줘.
공개 작업공간은 work/delphi-ai/rebuild-workspace를 사용하고,
평가 vault는 압축을 푼 저장소 밖의 별도 폴더를 사용해줘.
```

Codex는 저장소의 `.agents/skills/build-replica-operator/SKILL.md`를 따라 입력을
검증하고, 테스트를 공개 작업공간과 분리한 뒤 새 Operator를 작성하고 평가한다.
준비 완료 입력의 테스트나 기대값을 보고 구현을 맞추지 않는다.

## 주요 파일

- `README.md`: 전체 프로젝트와 CLI 설명
- `AGENTS.md`: Codex 작업 라우팅 규칙
- `skills/replica-research/SKILL.md`: 1차·2차 조사 및 실행 규칙
- `.agents/skills/build-replica-operator/SKILL.md`: 준비 완료 입력에서 Replica를 만드는 규칙
- `work/delphi-ai/delphi-ai-easy-result-ko.md`: Delphi 조사 결과의 쉬운 설명
- `work/delphi-ai/operator-workspace/.../report.md`: 생성된 Replica 평가 보고서

## 포함하지 않은 것

- 비공개 evaluator vault
- 사례별 비공개 출력과 채점 결과
- Python 캐시와 테스트 캐시
- 기존 중첩 ZIP 파일

