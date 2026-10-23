# 결론: 분류 규칙 수정의 범용 적절성

종료 사유: resolved. 근거: [001 Claude 제안](001-claude-proposal.md), [002 Codex 검토](002-codex-review.md).

## 합의
- 원칙은 범용적으로 타당: AI 자격 시험과 workflow 범위 분리, 비AI 지원 단계 보존, "standalone 호출"이 아닌 "독립된 고객 목적"으로 분리, 관계 4종의 공존 인정, 연결된 동작 기준 coverage.
- 현재 diff 그대로 확정은 보류. 확정 전 보완:
  1. 병합 기준 통일(I7): 목적·결과 명칭이 같다는 이유만으로 병합하지 않고 시작 조건·처리 책임·상태·완료 조건을 대조. SKILL.md:324 동일성 설명도 같은 기준을 참조.
  2. 지원 단계 포함 조건(I8): 관계 근거와 필수 단계 근거를 구별, 조건부 단계는 조건과 함께 보존, 관계 미확정 관찰은 단서로 남기고 정상 claim을 막지 않음.
  3. excluded 재분류 절차(I9): 원래 scope·항목·사유 보존, 재분류 항목에 안정 deferred ID·증거 부여, 제외 집계와 이력 구분.
  4. `not_workflow` 정의 확장(I2), worker 경계 절에 공통 규칙 링크(I1), 작성·실행을 각각 C0~A2로 판단(I5).
  5. orchestrator 절차에 claim 간 관계·누락 대조와 공유 기능 새 근거 시 관련 worker 재개 책임 추가(I3, I4).

## Claude 초기 의견 중 철회·축소
- I1 "worker 지침과 정면 충돌": 필요조건 문장이라 논리적 충돌 아님.
- I3 "coverage 확인 장치 없음": 과장. 단계 coverage 검증은 이미 존재.
- I4 "5·6번 이동 필수, 공유 기능 표현 불가": 기각.
- I5 "사례 특화": 기각.

## 사용자 결정 필요
- 위 보완을 반영할지, 범위(문서만 vs 검증기 `project.py`의 excluded 처리까지).
- overlap 설명을 `company-claims.json`에 노출할지(후속 구현 범위).
- I6 중복 구현 비용은 측정 전까지 보류.

## 검증 범위
- Claude: diff·worker 지침 대조, 검증기 excluded/집계 코드(project.py:540, 833) 확인.
- Codex: 관련 기존 테스트 6개 읽기 전용 실행 통과, `git diff --check` 통과. 전체 테스트·실제 research worker 실행은 하지 않음 → worker 행동 변화 효과는 미검증.

## 사용자 결정과 반영 (2026-10-22)

사용자가 Claude의 반영 범위 제안을 승인했고("그럼 그거 반영해봐"), 문서만 수정했다. 커밋 전이다.

반영 (`skills/replica-research/SKILL.md`, `skills/replica-research/agents/replica-first-pass.md`):
1. I7 병합 기준: 규칙 3에 시작 조건·처리 주체·유지 상태·완료 조건 비교 추가, 정규화 절의 동일성 정의가 규칙 3을 참조.
2. I8 지원 단계 포함 조건: 규칙 4에 "완료 결과까지의 경로에 있을 때만 필수, 관계 미확정 관찰은 claim을 막지 않음" 추가.
3. I2 `not_workflow` 정의에 관계 미확정 비AI 지원 단계 추가. 새 사유 값 없음.
4. I1 1차 지침 경계 절에 SKILL.md 참조와 "standalone 접근만으로는 부족" 추가, 탈락 절에 `no_ai_attribution` 전 지원 단계 확인 추가.
5. I5 규칙 1에 작성·실행을 각각 C0~A2로 판정한다는 문장 추가.
6. I3·I4 정규화 5번에 claim 간 누락 대조·excluded 확인, 2차 "Spawn and collect"에 공유 기능 새 근거 시 관련 worker 재실행 추가.
7. I9 Codex 안(재분류 절차·이력 구분)과 달리 `excluded`를 "독립 AI claim으로서의 탈락"으로 정의. 탈락 기록은 유지하고 claim에 출처·단계를 붙인 뒤 `replication_leads[].finding`에 인용. 제외 수 중복과 이력 손실이 모두 생기지 않아 검증기(`project.py`)를 바꾸지 않음. 규칙 6의 overlap 보고는 `finding`·판단 근거 기록으로 바꾸고, 최종 결과가 자동 표시하지 않는다는 한계를 명시.

반영하지 않음: 5·6번 이동(I4), 예시 삭제(I5), 공유 구현 공통화(I6), 새 enum·검증기 수정, `company-claims.json` overlap 자동 표시.

함께 갱신: `context/project-direction.md`(5절 "claim 경계는 고객 작업 단위로…"), `README.md` 1차 절.

검증: `PYTHONPATH=src python -m unittest discover -s tests` 451개 통과, `git diff --check` 통과. 실제 기업 조사는 미실행. 기존 조사 결과에는 적용되지 않으므로 새 작업 폴더에서 1차부터 다시 실행해야 한다.
