# Replica: 실제 체험과 근거가 보이는 AI 평가 — 토론 요청

작성일: 2026-10-14 (Asia/Seoul). 이 채팅의 사용자가 요청한 새 토론이다.

## 사용자 원문과 범위

출처: 현재 Codex 대화. 다음 원문은 의도·권한의 근거이며, 제품에 관한 사실은 코드와 실행 산출물로 확인한다.

- 사용자: “근데 우리는 전문가도 없고 공개된 시험이나 뭐 원제품도 없는데? 그래서 실제로 복제품을 사람이 쓸수있는 수준으로 만들어서 AI의 평가는 이렇고 니가 한번 써보고 판단하세요가 가능한거잖아”
- 사용자: “그럼 그 기준으로 지금 replica에서 이미 되는 거랑 부족한 거, 우선적으로 바꿔야 할 거 다시 정리해봐”
- 토론 요청: “클로드랑 토론한번 해봐 이 주제를 가지고”

토론 주제는 실제로 쓸 수 있는 복제품, 근거가 보이는 AI 평가, 새 입력으로 확인할 수 있는 체험을 중심으로 현재 기반·공백·다음 변경 우선순위를 정하는 것이다. REA·Ralph와의 차별화는 배경이며, 독점적 경쟁력이나 원제품 동등성을 이미 입증한 것으로 간주하지 않는다.

## 확정된 제약

- 전문가·공개 정답 시험·원제품 접근은 현재 확보되지 않았다는 사용자 전제다. 확보를 정상 실행의 선행 조건으로 요구하지 않는다.
- 기업 입력 이후 조사·구현·시험·비용·보고·앱 제공까지 자동 완료한다. 사람이 직접 써보거나 판단하는 것은 선택이며 완료 관문이 아니다.
- 복제품은 사람이 새 입력으로 실제 작업할 수 있는 웹 앱이다. AI와 사람은 같은 구현의 사용자 작업 경로를 사용한다. 원제품 UI의 시각적 복제는 요구하지 않는다.
- 기능마다 구현자 하나, 최종 시험·판정은 외부에서 한다. 공개 계획은 구현 전에 고정한다. 관측 없는 성공, 실패를 기술 장벽으로 해석, 원제품 동등성 추정은 금지한다.
- 여러 기능은 공통 기업 앱의 경로별 기능으로 제공하되 기능 간 데이터 공유는 필수가 아니다.
- 이번 권한은 토론과 문서 작성이다. 제품 코드·기존 실행 산출물·project-direction.md·다른 참여자 보고서는 수정하지 않는다. 사용자 대신 로드맵이나 제품 정책을 확정하지 않는다.
- 작업 트리에 평가 비용 개선 관련 미커밋 변경이 있다. 이를 보존한다. context/execution-resume.md의 완료된 실험을 재개·재실행하지 않는다. 기존 앱 상태 변경·원제품 로그인·클라우드 배포도 범위 밖이다.

## 논의할 쟁점

- I1: '실제 사용 가능'을 어떤 최소 완료 조건으로 확인할 것인가? 스크립트 예시나 HTTP 200과 구별하되 새 외부 정답을 요구하지 않을 것.
- I2: 구현 가능성과 AI 평가 가능성을 어떻게 구별할 것인가? AI 도구 제약 때문에 기능을 빼지 않으면서 미평가 기능을 무조건 성공으로 올리지 않을 것.
- I3: 유효한 관측 참조 없는 passed, 파일 검사 근거, 업로드 입력·평가 버전 고정 중 즉시 필요한 보완은 무엇인가?
- I4: 공통 기업 앱에서 평가·한계·근거·직접 체험을 연결하는 최소 변경은? 별도 기술평가 앱 통합보다 우선해야 하는가?
- I5: 직접 확인할 지점과 기업에 요청할 자료를 실제 관측에서 만드는 방식은? 질문 생성이 전문 정답 없는 상황에서도 유용하려면 무엇이 필요한가?
- I6: 실제 다음 작업 1개와 뒤따를 2~3개를 정하라. 외부 평가 검증·원제품 비교·다중 구현 비교의 시점도 정하되 현 실행 완료 조건으로 넣지 말 것.

## 이미 있는 Codex 제안

직전 답변을 001-codex-proposal.md로 보존한다. 이것은 진행자의 제안이지 사용자 승인·구현 완료가 아니다. Claude는 제안의 전제와 우선순위를 독립적으로 검토하고 과도하거나 빠진 부분을 지적한다.

## 필요한 근거 위치

프로젝트 /Users/cho/replica-mvp:
- context/project-direction.md, context/execution-resume.md, skills/replica-research/SKILL.md
- src/replica_mvp/company_app.py: _menu, company_features, check_company_app
- src/replica_mvp/bundle_runtime.py: _open_workspace, web_app_session
- src/replica_mvp/web_demo.py: validate_demo_plan, _evaluate_case, freeze_demo_plan, web_reproduction_status, render_demo_report
- src/replica_mvp/web_evaluation.py, web_checkpoint.py, agent_harness.py (_demo_scope, _claim_architecture, _company_results)
- tests/test_web_demo.py, test_web_evaluation.py, test_company_app.py, test_web_comparison_inputs.py
- docs/evaluation-efficiency-2026-10-13.md (보고서의 테스트는 이번 토론에서 수행한 테스트가 아님)
- work/delphi-ai-v4/claim-001-cost-comparison-2026-10-13/final-results/company-claims.json
- 위 결과가 참조하는 plan, demo-result.json, report.md, architecture의 excluded_parts. 현재 10개 사례/35개 조건 충족과 전체 부분 재현을 구분할 것.

별도 /Users/cho/replica-review-mvp (읽기 전용):
- AGENTS.md, README.md
- src/domain/model.ts, analysis.ts, research.ts, importer.ts, exporter.ts
- src/components/ClaimDetail.tsx
질문·검토 이력은 존재하지만 현재 importer는 research.json v1/v2 중심이고 company-claims 실행 결과를 받지 않는다. 이 판단도 코드에서 검증하라.

외부 배경(필요할 때만): https://github.com/namuh-eng/ralph-to-ralph, https://github.com/morluto/rea. 새 시장 조사·새 기업 실행은 필요 없다.

## 완료 기준

각 쟁점에 수용·수정·기각·미확인과 근거가 있고, 중요한 반론을 반영한 수정안까지 재검토돼야 한다. 최종 결론에는 현재 되는 것, 핵심 부족, 권고 우선순위, 첫 구현의 완료 기준, 후순위·재검토 조건, 실제 검증 범위를 남긴다. 모델 간 합의를 사용자 승인이나 실무 신뢰 입증으로 표현하지 않는다.
