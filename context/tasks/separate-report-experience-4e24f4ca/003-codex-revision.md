# Codex 수정안: 보고서·복제품 분리 (S1~S7)

이 제안은 구현이나 사용자 결정이 아니다. 앱은 기능을 수행하고, 보고서는 평가 판단과 근거를 설명한다. 자동 종료, 보고서 생성, 앱 제공 상태는 별도로 기록한다.

## S1~S3. 책임·완료·연결

**S1 — 수용.** 앱에는 기능 사용법과 지원 범위를 둔다. 평가 판정·근거·한계·질문은 보고서에 둔다. 사람과 AI는 같은 웹 작업 경로를 사용한다.

**S2 — 수정.** 앱을 만들 수 없는 주장이나 차단된 실행도 전체 실행은 종료될 수 있다. 따라서 종료와 앱 제공을 동일시하지 않는다.

- **실행 종료:** 각 조사 주장의 실행 결과와 미실행·차단 상태가 기록됨.
- **보고서 생성:** 기존 보고서와 결과 JSON이 생성됨.
- **앱 제공 상태:** 기동 점검 시각, 기능별 로드 여부와 제외·실패 사유를 기록함.

`assembled`는 첫 화면 기동을 뜻한다. 기능 품질이나 현재 서버 생존을 보증하지 않는다. 로컬 실행 명령도 평가자가 접근 가능한 앱 제공과 같은 뜻으로 쓰지 않는다.

**S3 — 조건부 수용.** 기존 `company-claims.json`, `architecture.md`, `report.md`를 재사용한다. 보고서에는 평가 시각의 앱 상태와 `claim_id`, `scenario_id`, 실행 식별자, 계획·대상 구현 해시를 연결한다. `report.md`에는 claim 및 계획·manifest 해시가 이미 있고, 기업 앱 상태와 기능별 경로는 결과 JSON과 architecture 문서에 기록된다. 빠진 상호 링크와 `scenario_id`, `checked_at`만 보완한다. 정적 보고서에는 현재 접속을 약속하는 오래된 URL 대신 점검 당시 상태를 쓴다. [Claude 검토](</Users/cho/replica-mvp/context/tasks/separate-report-experience-4e24f4ca/002-claude-review.md>)

## S4~S5. 첫 작업과 후속 우선순위

**첫 작업은 근거 참조 검증과 기존 보고서 연결의 필요한 보완으로 한정한다.** 별도 화면을 만들거나 링크 블록만 추가하는 작업으로 끝내지 않는다.

- 새 판정은 같은 실행·사례의 실제 근거를 참조해야 한다. 근거 종류에는 행동 이벤트뿐 아니라 초기·중간·최종 화면, 파일, 결정적 검사도 포함한다.
- 없는 참조나 다른 사례·실행의 참조는 거부한다. 유효 근거가 하나도 없으면 원응답과 차단 이유를 보존하고 `not_evaluated`로 처리한다.
- 이는 참조 무결성을 확인하는 일이다. 참조 존재만으로 판단의 의미상 정확성을 보증하지 않는다.
- 기존 `report.md`와 `architecture.md`를 상호 연결하고 누락된 실행 식별자·앱 점검 시각·제공 상태를 추가한다. 완료된 결과를 다시 쓰거나 승격하지 않는다.

이후 우선순위는 다음과 같다.

1. **모든 신규 평가 전에 업로드 내용 동일성 기록을 보강한다.** 고정 업로드와 생성 업로드 모두 내용 해시를 실행 및 재개 기록에 연결한다.
2. **새 자료로 실제 업무를 수행했는지 확인한다.** 해시 생성만으로 검증을 끝내지 않는다. 새 자료를 같은 웹 화면에 넣어 계획된 업무 단계를 거쳐 결과를 받았는지 기록한다. 성공하지 못하면 실패·미평가·미실행을 구별한다.
3. **질문의 출처를 나눠 진행한다.** 공개 주장에 조건·근거가 빠져 생기는 질문은 웹 평가 참조 검증을 기다리지 않고 보고서에서 초안으로 만들 수 있다. 재현 관측에서 나오는 질문은 근거 검증 후에 생성한다. 외부 발송은 포함하지 않는다.

## S6. Delphi 앱 제공 상태 정정

002의 “Delphi v4 미제공” 단정은 최신 기록과 맞지 않아 정정한다. `execution-resume.md`는 당시 `127.0.0.1:49770`에서 메뉴와 `/claim-001/`이 HTTP 200이었다고 기록한다. Delphi v4 결과 JSON도 `company_app.status: assembled`, `claim-001`의 `loaded`, 점검 시각을 남긴다. 이는 **당시 첫 화면 제공 점검**의 근거다. 전체 업무 수행이나 현재 서버 접속 가능성을 뜻하지 않는다. 이번에는 서버에 접속하지 않았다. [실행 재개 기록](/Users/cho/replica-mvp/context/execution-resume.md:12) · [Delphi 결과](/Users/cho/replica-mvp/work/delphi-ai-v4/claim-001-cost-comparison-2026-10-13/final-results/company-claims.json:951)

## S7. 바인딩 해시와 사용자 체험 상태

지정된 경로만 읽어 확인했다. `_serve_company`는 `_read_registry`로 레지스트리를 읽고 `implementation_result.candidate_path`의 manifest와 mount 가능 여부를 확인한다. `company_app_session`이 `web_app_session`을 시작하고, 후자는 `_open_workspace`를 통해 작업 공간을 연다. [cli.py](/Users/cho/replica-mvp/src/replica_mvp/cli.py:532) · [agent_harness.py](/Users/cho/replica-mvp/src/replica_mvp/agent_harness.py:74) · [company_app.py](/Users/cho/replica-mvp/src/replica_mvp/company_app.py:124) · [bundle_runtime.py](/Users/cho/replica-mvp/src/replica_mvp/bundle_runtime.py:430)

구현 바인딩에는 `candidate_sha256`가 저장된다. 그러나 이 서빙 경로에서 그 값과 현재 manifest의 해시를 비교하는 코드는 확인하지 못했다. `_open_workspace`는 현재 manifest와 기존 세션 표식을 비교하고, 복사된 파일이 해당 manifest의 파일 해시와 맞는지 검사한다. 첫 복사도 manifest에 기재된 파일 해시를 검증한다. 이것은 현재 입력 manifest와 작업 사본의 일관성 검사이며, 평가 때 바인딩된 후보와의 동일성 검사가 아니다. [바인딩 기록](/Users/cho/replica-mvp/src/replica_mvp/agent_harness.py:1276) · [작업 공간 검사·복사](/Users/cho/replica-mvp/src/replica_mvp/bundle_runtime.py:192)

후속 수정에서는 서빙 시작 시 바인딩된 후보 해시와 현재 후보를 비교하고, 불일치하면 해당 앱을 평가 대상과 동일한 것으로 제공하지 않도록 한다. 사용자 체험은 별도 작업 공간의 복사본에서 수행하며, 체험 변경이 과거 평가 근거·보고서·결과를 수정하지 않는 원칙을 유지한다.

이번 턴은 지정 문서와 코드 경로를 읽기만 했다. 테스트, 서버 실행·접속, 기존 결과 변경, Delphi 재실행은 하지 않았다.
