# 분류 규칙 수정의 범용 적절성 검토

## 사용자 요청 (원문, 이 Claude 세션)

1. "지금 분류하는 부분 수정이 들어갔는데 범용적으로 봤을때 적절한거 같아?"
2. (Claude 검토 후) "이거가지고 codex랑 토론해서 결과 알려줘봐"

## 범위

- 대상: `skills/replica-research/SKILL.md`의 미커밋 diff (`git diff skills/replica-research/SKILL.md`).
  - "Qualify AI technology claims" 끝의 새 단락(C0~A2는 standalone AI claim 시험)
  - "Collect one claim per whole workflow"의 새 1~6번 규칙
  - 정규화 단계 5번 문구 변경
- 함께 볼 파일: `skills/replica-research/agents/replica-first-pass.md`, `skills/replica-research/agents/replica-second-pass.md`, `context/project-direction.md`, `src/replica_mvp/project.py`(제외 사유 목록).
- 질문: 이 수정이 특정 기업 사례가 아니라 임의 기업에 범용적으로 적절한가. 하위 지침·검증기와 일관된가. 무엇을 고쳐야 확정할 수 있는가.

## 제약

- 토론만 요청됨. 저장소 수정·커밋은 범위 밖 (사용자 메모: 설계 논의에서 저장소 수정은 확정 지시가 있을 때만).
- 프로젝트 방향: 기업 입력 후 사람 개입 없는 완전 자동, 웹 앱으로 체험, 봉인·JSON 시험으로 회귀 금지 (`context/project-direction.md`).

## 완료 기준

- 각 쟁점(I1~)에 대해 수용·기각·보류와 근거가 정리됨.
- 확정 전 필요한 수정 목록과, 사용자가 결정해야 할 항목이 구분됨.
