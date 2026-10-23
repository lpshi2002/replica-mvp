# Claude 초기 검토 (제안)

판단: 원칙(1~4번)은 범용적으로 타당하다. 그러나 SKILL.md만 바뀌고 하위 worker 지침이 옛 기준을 유지해 충돌하므로, 현 상태로는 실행에서 지켜지기 어렵다.

## 타당한 점
- AI 자격 시험(C0/C1/A1/A2)과 workflow 범위를 분리. 비AI 지원 단계(검색·권한·저장·알림)를 workflow에 보존 → AI 부분만 재현해 고객 결과에 못 미치는 문제 방지.
- 분리 기준을 "standalone 호출 가능"에서 "독립된 고객 목적·완료 결과"로 변경. API/UI, JSON/prose, 채널 차이는 전달 변형.
- 관계 4종(내부 단계, 다른 전달 인터페이스, 공유 기능, 이벤트/일정 후속 workflow)과 공존 가능성 명시.
- 5번 "연결된 동작이 coverage" — 부품 테스트 통과 ≠ 전체 workflow 성공.

## 쟁점
- **I1 1차 worker 지침 충돌.** `agents/replica-first-pass.md:73-75`는 "standalone product, endpoint, or separately documented workflow면 별도 claim". 새 3번은 "standalone invocation은 근거일 뿐 충분하지 않다". 새 문구가 "worker 지침은 이 규칙에 종속"이라 선언하지만 worker는 자기 지침을 먼저 읽고, "assignment에 이 섹션 포인터 포함" 요구가 worker Input 목록(`replica-first-pass.md:13-21`)에 없다.
- **I2 no_ai_attribution / not_workflow.** 새 4번은 no_ai_attribution 탈락 전 지원 단계로 붙이거나 `not_workflow`로 보류하라 함. worker 지침 `replica-first-pass.md:87`은 여전히 확정 탈락 사유. `not_workflow` 정의(`SKILL.md:148`)는 model/platform property/UI/architecture/mechanism뿐이라 비AI 지원 단계(알림·저장)를 포괄하지 못함.
- **I3 존재하지 않는 장치.** 6번 "Report overlapping scope explicitly"에 대응하는 필드·출력 없음(`src/`, SKILL, worker 지침 검색 결과 overlap 처리 없음). "checks scope coverage again before freezing pass 2"에 대응하는 절차 단계 없음.
- **I4 책임 위치.** 1차 수집 섹션이 2차 `step_coverage`, 구현 경로, 데모 기대, 최종 집계까지 규정. 5·6번 후반부는 2차 지침/평가 섹션에 있어야 2차 worker가 읽는다. 2차 merge 기준(`replica-second-pass.md:154-164`)은 "독립 전달 여부" 이분법이라 "별도 claim이면서 다른 workflow의 단계"인 공유 기능을 표현할 수 없음.
- **I5 사례 특화 흔적.** "An external coding agent authoring an automation", "search inside conversation + search API"는 최근 사례 일반화의 흔적으로 보임. 원칙 문장(설정/작성 vs 실행 구분)은 범용.
- **I6 구현 중복 비용.** 공유 기능을 사용하는 모든 claim에 포함(3번 끝) → claim마다 같은 기능 재구현. brief 자기완결성 때문에 필요할 수 있으나 의도 확인 필요.

## 권고
1. 1차 worker 지침의 충돌 문장(73-75, 87행) 수정 + Input에 섹션 포인터.
2. `not_workflow` 정의 확장 또는 비AI 지원 단계용 보류 사유 신설.
3. 5·6번 구현·평가 규칙은 2차 지침/평가 섹션으로 이동, 없는 절차(overlap 보고, freeze 전 coverage 재확인)는 신설하거나 삭제.
