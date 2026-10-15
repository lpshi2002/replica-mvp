# 기존 Replica에 필요한 세 변경의 구현 방법

2026-10-15 (Asia/Seoul). 사용자 요청 출처: 현재 Codex 대화.

## 사용자 요청과 현재 범위
사용자: “그니까 그걸 이제 어떻게 해야하냐 이거야 이미 구현이 되어있는게있잖아”
진행자는 기존 코드 대조 후 세 변경을 제안했다. 사용자: “그거 클로드랑 어떻게 할지 토론해보고 결론 말해줘”.
보고서 작성·개선·질문 생성은 보류다. 기업 앱과 보고서는 별도다. 복제품 시험과 실행 기록이 나중에 기업 설명, 재현/미재현 범위와 이유, 시간·비용, 우리 결론을 뒷받침해야 한다. 이번 요청은 구현 방법 토론이며 제품 코드 수정 요청은 아니다.

이전 토론들은 종료됐다. context/tasks/experience-evidence-priority-57f0541a, separate-report-experience-4e24f4ca는 배경이다. 이번에는 제품 전략을 반복하지 않고 기존 코드에 세 변경을 어떻게 넣을지만 정한다. 001에는 현재 대화의 명시적 제안을 보존한다.

## 이미 있는 기능과 제약
- 기업 앱 셸, 기능별 경로, AI의 같은 웹 화면 시험, 사용자 체험 상태 분리, 개발 로그, 미실행/실패/미평가 구별, 누적 웹 시험 비용·개발/조사 세션 사용량 집계가 있다. 재구축하지 않는다.
- second_pass에 excluded_parts, alternatives, needs와 부분 재현 집계가 있다. CLI의 한계를 앱 한계로 삼지 말라는 조사 지침도 있다. 제외 사유 재검토는 별도 기존 자료 검토이며 새 분류 플랫폼을 만들지 않는다.
- 사람이 실제 써보는 것은 선택, 기업 입력 이후 자동 완료. 전문가·원제품·공개 정답 시험·숨긴 시험 도입·사용자 승인 단계는 선행 조건이 아니다.
- 공개 변형 규칙은 구현 전에 고정, 실제 값은 평가 때 생성. 동결한 기준/업무 범위를 구현 출력에 맞춰 낮추지 않는다.
- 기존 결과·계획·입력·수치 보존. legacy에 해시를 소급 붙여 당시 고정됐다고 하지 않는다. 완료된 Delphi 기업 실험·앱 재실행/상태 변경 금지.
- 현재 작업 트리는 기존 코드 변경 및 .claude/settings.json 변경이 있다. 제품 코드·설정·공유 방향 문서 수정 금지. 참여자는 지정된 의견 파일만 작성한다.

## 쟁점
P1. 근거 참조 검증: _evaluate_case의 무효 ID 필터 후 passed 유지 결함. 초기 화면/행동/파일/결정적 검사에 어떤 최소 식별/보존 계약을 쓰는가? 판정 스키마/결과 필드/호환성/재개에 필요한 변경과 부정 사례를 명확히. 참조 존재와 의미상 정확성은 다르다.
P2. 제공 버전 확인: _serve_company가 bound candidate_sha256를 직접 대조하지 않는 경로. 기존 검증을 어디에 재사용하고 CLI/company_features 중복을 얼마나 정리할까? 완전 성공만 사용 허용하지 말고 부분 재현/미평가 구현 제공을 보존. 미평가 앱을 평가 완료로 표시하지 않음.
P3. 업로드 파일 변형: 현재 _instance_case가 문구만 바꾸고 업로드는 같은 파일. 고정 파일 내용 해시와 실행 때 생성한 새 파일을 어디에 보존하고 계획/질문/사실/검사값과 일치시키는가? 기존 입력 재사용·재개 계약에 어떻게 연결하는가? TXT/CSV 등 작은 첫 범위를 선택하되 기업의 다른 입력 요구를 몰래 삭제하지 말 것. 생성 실패/비지원 형식 처리를 명시.
P4. 변경 순서와 최소 검증: 세 묶음을 작은 구현 단위로 나누고 각 완료 기준/테스트, 기존 기록 호환, 변경하지 않을 기존 기능을 결정. 단순히 계획을 반복하지 말고 함수/파일/자료 흐름으로 제안.

## 우선 읽을 근거
- context/project-direction.md 맨 위와 5절의 보고서/질문 보류; context/execution-resume.md는 완료된 평가 재실행 금지.
- src/replica_mvp/web_demo.py: JUDGE_SCHEMA, validate_demo_plan, _judge_prompt, _run_case, _evaluate_case, freeze_demo_plan, _instance_prompt, _instance_case, run_web_demo
- src/replica_mvp/web_checkpoint.py: load_checkpoint, load_input_cases (계획/manifest/평가기/설정/관측 파일 검증은 이미 있음)
- src/replica_mvp/cli.py: _serve_company
- src/replica_mvp/company_app.py: company_features, check_company_app
- src/replica_mvp/bundle_runtime.py: copy_bundle, _open_workspace, web_app_session
- src/replica_mvp/agent_harness.py: _validate_bound_artifact, _validate_implementation_result, finish_agent_harness, _company_results
- src/replica_mvp/single_agent.py: validate_single_implementation
- tests/test_web_demo.py, test_web_evaluation.py, test_web_comparison_inputs.py, test_company_app.py

finish 단계는 이미 최종 결과/구현 검증을 호출한다. 그 검증과 serve-company 경로의 공백을 구별할 것. 현재 누적 비용 집계가 있어 옛 방향 문서의 미합산 기록만으로 새 결함을 주장하지 말 것. 최신 Delphi 기록은 당시 assembled/loaded였다; 현재 생존은 미확인이다.

## 완료 기준
기존 재사용 범위, 실제 새로 바꿀 곳, 데이터/실행 흐름, 실패·호환 정책, 작은 변경 순서와 검증 기준을 합의/이견으로 정리한다. 중요한 반론은 Codex 수정과 같은 Claude 재검토까지 진행한다. 코드 읽기/작은 임시 재현은 가능하지만 전체 테스트·기업 실행은 필요하지 않다. 모델 합의를 구현 완료나 사용자 정책 승인으로 표현하지 않는다.
