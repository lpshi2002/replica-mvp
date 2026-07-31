# FurtherAI 1차 주장 요약과 재검토

## 먼저 알아둘 점

이 문서는 기존 `work/furtherai/research.json`의 30개 발견 기록을 현재 1차 기준으로 다시 판정한 결과다. 새 자료를 조사한 것이 아니라, 저장된 출처와 인용만 사용해 C0·C1·A1·A2를 다시 적용하고 하위 기능을 상위 E2E 워크플로우에 병합했다.

현재 근거를 고객의 처음 요청부터 최종 결과까지 묶으면 대략 다음처럼 나뉜다.

- 최종 고객 대상 AI E2E 주장: 12개
- 상위 주장에 흡수된 하위 기록: 13개
- 별도 주장으로 통과하지 못한 기록: 5개

따라서 FurtherAI가 고객에게 제공한다고 직접 주장하는 AI 워크플로우 수는 현재 근거 기준 **12개**다. 모든 조사 범위를 이미 함께 본 상태이므로 근거가 부족한 기록은 더 이상 보류로 남기지 않고 제외했다.

## 2차 조사 전달 목록

2차 조사에는 아래 **12개 상위 E2E 주장만** 전달한다. 포함된 하위 ID는 해당 상위 주장의 단계·변형·추가 근거이며 별도 2차 조사 건으로 세지 않는다.

| 2차 기준 ID | 전달할 E2E 주장 | 함께 흡수된 기존 ID | 2차 전달 |
|---|---|---|---|
| 001 | 제출 접수·인수 준비 | 002, 003, 004, 005, 008, 028 | 전달 |
| 006 | 증권 검증·비교 | 007 | 전달 |
| 009 | 인수·거래 감사 | 010 | 전달 |
| 011 | 보험 제안서 생성 | 없음 | 전달 |
| 013 | 갱신 검토 | 없음 | 전달 |
| 015 | 증권 발행 QA | 없음 | 전달 |
| 016 | 보험금 접수·문서 처리 | 017 | 전달 |
| 018 | 보험금 지급 reconciliation | 없음 | 전달 |
| 019 | 보험금 감사·사기 탐지 | 021 | 전달 |
| 020 | 손실 예방·위험 조정 | 022 | 전달 |
| 023 | 보험 규제준수 모니터링 | 024 | 전달 |
| 025 | 출처 기반 보험 조사 | 027 | 전달 |

다음 ID는 2차로 넘기지 않는다: `012`, `014`, `031`, `032`, `033`. 병합된 하위 ID 역시 독립 건으로는 넘기지 않는다.

## 전체 흐름으로 보면

| 상위 E2E 주장 | 포함되는 기존 기록 | 하나로 보는 이유 |
|---|---|---|
| 제출 접수·인수 준비 | 001–005, 008, 028 | 이메일·첨부 접수에서 추출·검사·위험요약·triage까지 한 제출 건을 처리하는 같은 고객 업무 |
| 인수 감사 | 009, 010 | 제출·증권 자료를 기준과 대조해 감사 결과를 내는 같은 업무 |
| 증권 검증·비교 | 006, 007 | quote·binder·issued policy를 검증하고 차이를 보여주는 하나의 증권 QA 업무 |
| 보험 제안서 생성 | 011 | carrier quote를 비교해 고객에게 전달할 제안서를 만드는 별도 업무 |
| 갱신 검토 | 013 | 기존 증권과 새 자료를 모아 갱신 판단용 pack을 만드는 독립 업무 |
| 증권 발행 QA | 015 | 인수 통과 후 발행자료 완결성을 확인하는 별도 업무 |
| 보험금 접수·문서 처리 | 016, 017 | FNOL과 첨부를 구조화·검증해 라우팅 가능한 claim record로 만드는 같은 접수 업무 |
| 보험금 지급 reconciliation | 018 | 접수 이후 대량 지급을 대조·승인하는 별도 업무 |
| 보험금 감사·사기 탐지 | 019, 021 | 지급 전 청구 자료를 검사해 mismatch·leakage·사기 위험을 표시하는 같은 통제 업무 |
| 손실 예방·위험 조정 | 020, 022 | 실시간 위험을 감지해 손실 전 알림이나 보험조건 조정으로 이어지는 예방 업무 |
| 보험 규제준수 모니터링 | 023, 024 | 증권과 규칙을 계속 대조해 예외·drift·감사 근거를 내는 같은 업무 |
| 출처 기반 보험 조사 | 025, 027 | 질문을 받아 내부 문서 또는 실시간 웹 출처에 근거한 답변을 내는 같은 조사 업무 |

## 주장별 설명

| ID | 기존 주장과 입출력 | 왜 AI라고 가져왔나·핵심 근거 | 경계 판단과 현재 판정 |
|---|---|---|---|
| 001 제출 처리·triage | SOV·ACORD·loss run 등 제출물 → 정규화·검증된 인수 요약, triage, Salesforce 기록 | 공식 글이 `agent`가 17단계를 스스로 수행한다고 설명했다. [공식 근거](https://www.furtherai.com/blog/introducing-mentions-human-in-the-loop-ai-agents) | 17단계여도 한 제출 건을 인수 가능한 상태까지 처리하는 **상위 E2E 주장으로 통과**한다. 002–005·008·028은 단계나 입력·채널 변형으로 병합한다. |
| 002 인수 가이드라인 검사 | 제출 위험과 인수기준 → 이유와 감사기록이 있는 예외·gap | 회사가 `AI-powered checks`가 각 위험을 기준과 비교한다고 직접 적었다. [파트너 근거](https://www.furtherai.com/blog/furtherai-joins-the-accelerant-marketplace-a-partnership-helping-mgas-move-faster) | 가이드라인 검사는 제출 처리 중 인수 가능 여부를 정하는 단계이므로 별도 주장으로 늘리지 않고 **001에 병합**한다. |
| 003 복잡한 SOV 접수 | 형식이 제각각인 SOV → 검증·보강된 carrier schema SOV | 고객 사례가 FurtherAI의 `AI solution`이 E2E SOV intake를 자동화한다고 명시했다. [고객 근거](https://www.furtherai.com/customers/complex-property-sov-intake) | SOV는 제출 처리의 대표 입력 유형이다. 별도 제품으로 독립 실행된다는 근거가 추가되지 않으면 **001의 입력 변형과 단계 근거로 병합**한다. |
| 004 자기교정 loss-run 추출 | 복잡한 loss-run PDF → 검증된 손실 데이터와 export | 엔지니어링 글이 agent가 추출 결과를 검사하고 스스로 고친다고 설명했다. [기술 근거](https://www.furtherai.com/engineering-blogs/hardest-document-extraction-problem-in-insurance) | 추출·검증·수정·export를 쪼개지 않고 제출 처리에서 loss-run을 다루는 한 단계로 **001에 병합**한다. 독립 추출 서비스 근거가 있으면 그때 분리한다. |
| 005 Grid 문서 구조화 | 여러 형식의 보험문서 → 정렬된 구조화 열 | 제품 글이 `AI turns them into clean, structured columns`라고 직접 적었다. [제품 근거](https://www.furtherai.com/blog/ai-grid-a-faster-way-to-handle-insurance-data) | 구조화 표는 이후 검사·요약에 전달되는 중간 결과다. 현재 목적에서는 **001의 문서 구조화 단계로 병합**한다. |
| 006 증권 문서 검증 | quote·binder·issued policy → 일관성·준수 검증 결과 | 고객 페이지가 `Policy Check & Compare AI`의 자동 추출을 설명했다. [고객 근거](https://www.furtherai.com/customers/policy-check-compare-ai-teammate) | 증권 검증·비교의 **상위 E2E 주장으로 통과**한다. 추출·검증·차이 비교를 나누지 않고 007을 같은 업무에 병합한다. |
| 007 증권 packet 비교 | 여러 전체 증권 packet → 담보·조건·면책·endorsement 차이표 | 같은 고객 페이지가 AI solution의 side-by-side 비교를 설명했다. [고객 근거](https://www.furtherai.com/customers/policy-check-compare-ai-teammate) | 같은 제품이 증권 묶음을 검증한 뒤 차이를 보여주는 흐름이므로 **006에 병합**한다. 차이표는 그 E2E의 최종 결과 일부다. |
| 008 위험 분석 | 보험 검토 파일과 담보 → 투명한 위험 요약·담보 비교 | solutions 페이지가 `transparent AI`가 파일을 요약하고 의사결정을 돕는다고 적었다. [제품 근거](https://www.furtherai.com/all-solutions) | 위험 요약과 담보 비교는 인수자가 제출 건을 판단하기 위한 결과 패키지다. 별도 주장으로 쪼개지 않고 **001에 병합**한다. |
| 009 인수 감사 | 신청·증빙·증권과 MGA 기준 → match/mismatch 감사보고서 | 고객 사례가 `AI-driven solution`이 감사의 추출·검증을 자동화한다고 명시했다. [고객 근거](https://www.furtherai.com/customers/underwriting-audit-ai) | 제출 준비와 달리 이미 처리된 자료를 독립적으로 감사해 보고서를 내므로 **상위 E2E 주장으로 통과**하고 010을 편입한다. |
| 010 거래 감사 | 거래감사 자료 → 핵심 감사 insight | Accelerant가 FurtherAI를 감사 업무에 쓰고 AI agents를 배포한다고 설명했다. [파트너 근거](https://www.furtherai.com/blog/furtherai-joins-the-accelerant-marketplace-a-partnership-helping-mgas-move-faster) | 고객 목적과 결과가 같은 감사 유형이므로 **009 인수 감사에 병합**한다. |
| 011 제안서 생성 | 두 carrier quote → 검토 가능한 규정준수 제안서 | broker 제품 페이지가 `our AI aggregates quotes, compares coverages, and generates polished presentations`라고 직접 설명했다. [제품 근거](https://www.furtherai.com/segment/brokers) | 제출 triage와 최종 산출물이 다르므로 **독립 E2E 주장으로 통과**한다. |
| 012 Portfolio Insights 정규화 | 흩어진 portfolio spreadsheet → 분석용 표준 데이터 | 같은 solutions 페이지의 `AI built for real insurance workflows`와 Portfolio Insights 설명을 묶었다. [제품 근거](https://www.furtherai.com/all-solutions) | AI와 해당 작업을 같은 문장에서 직접 연결하지 못하므로 `no_ai_attribution`으로 **제외**한다. |
| 013 갱신 pack 생성 | 증권·노출·손해이력·새 제출물 → 출처가 달린 갱신 요약 | 공식 글이 AI가 policy terms·claims·risk signals를 모아 갱신 요약을 만든다고 설명했다. [공식 근거](https://www.furtherai.com/blog/automated-policy-renewal-review-tools) | 자료 수집부터 비교·검증·요약까지 포함한 **독립 E2E 주장으로 통과**한다. |
| 014 Bordereaux 생성 | 증권·프로그램 자료와 carrier template → 검증된 bordereaux | 기존 근거는 FurtherAI `AI workspace`가 보험용이라는 일반 문장뿐이었다. [공식 근거](https://www.furtherai.com/blog/automate-underwriting-summary-audit-capabilities-mga) | AI가 bordereaux 추출·매핑을 한다는 직접 문장이 없어 `no_ai_attribution`으로 **제외**한다. |
| 015 증권발행 문서 검증 | 인수 통과 위험과 발행자료 → 정리·완결성 확인된 발행자료 | 파트너 글이 `FurtherAI agents`가 자료를 정리하고 완결성을 검증한다고 직접 적었다. [파트너 근거](https://www.furtherai.com/blog/furtherai-partners-with-guidewire-to-close-a-long-standing-gap-in-insurance-ai) | 발행자료 QA로 완결되므로 **독립 E2E 주장으로 통과**한다. 정리와 검증은 단계다. |
| 016 보험금 접수·라우팅 | 여러 채널 FNOL·문서·증권 → 구조화·담보검증·점수·라우팅된 claim record | 공식 글이 FurtherAI `AI workspace`가 claim intake부터 검토·검증·보고를 자동화한다고 설명했다. [공식 근거](https://www.furtherai.com/blog/best-ai-claims-processing-and-adjudication-tpas) | 접수·추출·담보검사·분류·라우팅 전체를 포함한 **상위 E2E 주장으로 통과**하고 017을 편입한다. |
| 017 Claims Document Intelligence | 의료비·청구문서·이미지 → 검증된 searchable case와 구조화 필드 | 공식 글이 LLM, NLP, computer vision이 각 입력을 처리한다고 구체적으로 설명했다. [기술 근거](https://www.furtherai.com/blog/automated-medical-bill-data-extraction) | searchable case와 구조화 필드는 보험금 접수 이후 라우팅에 쓰이는 중간 결과이므로 **016에 병합**한다. OCR·NLP·vision도 그 안의 단계다. |
| 018 보험금 지급 reconciliation·승인 | 대량 지급업무 → reconciliation과 승인 처리 | Guidewire 자료가 `AI Assistants`가 payment reconciliation과 approvals를 자동화한다고 직접 적었다. [Marketplace 근거](https://marketplace.guidewire.com/sfc/servlet.shepherd/version/download/068PW00001LDezCYAT) | 접수와 별도로 지급 담당자가 시작하고 승인 처리로 끝나는 **독립 E2E 주장으로 통과**한다. |
| 019 건강보험 청구 감사 | 전체 청구 pack·담보기준·원가기준 → mismatch·가격이상·leakage 추정 | 공식 글이 FurtherAI `AI workspace`가 line item을 추출·정규화·비교한다고 설명했다. [공식 근거](https://www.furtherai.com/blog/claims-leakage-fraud-detection-software-for-carriers) | 청구자료 검사부터 leakage·사기 위험 표시까지의 **상위 E2E 주장으로 통과**하며 021을 병합한다. |
| 020 청구 예방 알림 | 과거 청구와 실시간 sensor·날씨·행동 → 손실 전 예방 알림 | 공식 글이 AI가 과거 청구와 실시간 feed를 분석한다고 직접 적었다. [공식 근거](https://www.furtherai.com/blog/ai-powered-claims-prevention-how-insurers-can-reduce-risk-before-a-claim-even-happens) | 위험 감지부터 예방 알림과 보험조건 조정까지의 **상위 E2E 주장으로 통과**하고 022를 후속 조치로 병합한다. |
| 021 지급 전 사기 탐지 | 청구자료·문서·이미지·통화·텍스트 → 지급 전 suspicious flag | 같은 공식 글이 AI가 지급 전에 fraud를 탐지한다고 직접 적었다. [공식 근거](https://www.furtherai.com/blog/ai-powered-claims-prevention-how-insurers-can-reduce-risk-before-a-claim-even-happens) | suspicious flag는 지급 전 청구 감사의 판단 결과이므로 별도 주장으로 늘리지 않고 **019에 병합**한다. |
| 022 동적 보험료·담보 조정 | 운전·날씨·재산·사이버 위험 변화 → 보험료·담보 조정 | FurtherAI가 insurers에게 `AI-driven policy adjustments` 도구를 제공한다고 적었다. [공식 근거](https://www.furtherai.com/blog/ai-powered-claims-prevention-how-insurers-can-reduce-risk-before-a-claim-even-happens) | 같은 실시간 위험 입력을 사용해 손실 전 행동을 만든다. 추천과 적용 범위는 출처대로 제한하되 **020의 후속 결과로 병합**한다. |
| 023 보험 규제준수 검토 | 제출·quote·증권과 규정·인수·재보험 규칙 → 예외와 감사증거 | 공식 글이 FurtherAI를 compliance-first `AI workspace`라 부르고 policy review와 reporting을 직접 설명했다. [공식 근거](https://www.furtherai.com/blog/ai-compliance-review-underwriting) | 규칙 대조부터 예외·감사증거까지의 **상위 E2E 주장으로 통과**한다. |
| 024 지속적 policy compliance monitoring | quote·endorsement·renewal·cancellation과 규칙 → drift alert·감사기록 | 공식 글이 LLM과 document AI가 증권을 규정·가이드라인·treaty에 대조한다고 직접 적었다. [공식 근거](https://www.furtherai.com/blog/ai-compliance-review-underwriting) | 같은 규제준수 업무의 지속 모니터링 단계와 출력이므로 **023에 병합**한다. |
| 025 출처 기반 보험 Assistant | 질문과 보험문서 → 인용 가능한 설명형 답변 | 제품 페이지가 `AI Assistant`가 복잡한 보험문서 질문에 source-backed 답을 준다고 명시했다. [제품 근거](https://www.furtherai.com/product) | 질문에서 출처가 달린 답변까지의 **상위 E2E 주장으로 통과**한다. 검색과 답변 생성은 단계이고 027은 외부 출처 변형으로 병합한다. |
| 027 실시간 보험 Web Search | 자연어 위험·시장·규제 질문 → 검증된 실시간 출처의 인용 답변 | 출시 글이 `AI-driven answers`와 verified real-time source를 직접 연결했다. [출시 근거](https://www.furtherai.com/blog/introducing-web-search-in-furtherai) | 내부 문서 대신 실시간 웹을 본다는 차이만 있고 최종 목적이 같은 인용 답변이므로 **025에 병합**한다. |
| 028 Outlook 제출 지원 | 열린 이메일·첨부 → triage, 위험요약, next step, 답장초안, 행동기록 | 출시 글은 `Agentic Workspace`가 triage와 답장작성을 한다고 설명했다. [출시 근거](https://www.furtherai.com/blog/furtherai-outlook-plugin-launch) | Outlook은 제출 업무의 유입 채널이므로 출력들을 쪼개지 않고 **001에 병합**한다. |
| 031 제출 profile deck | 인수 제출물과 요청 → 위원회용 profile deck | Code Gen 글이 AI 모델의 code generation과 FurtherAI Code Gen 출시를 설명했다. [출시 근거](https://www.furtherai.com/blog/furtherai-code-gen) | AI가 코드를 쓴다는 문장과 FurtherAI의 deck 생성 문장이 분리돼 있어 `no_ai_attribution`으로 **제외**한다. |
| 032 Portfolio dashboard | portfolio와 시각화 요청 → 갱신되는 dashboard | 같은 글이 assistant가 dashboard를 만든다고 사례를 들었다. [출시 근거](https://www.furtherai.com/blog/furtherai-code-gen) | 031과 같은 근거 결함이 있어 별도 주장으로 두지 않고 **제외**한다. |
| 033 Program microsite | 보험 program 정보 → broker용 microsite | 같은 글이 program manager용 microsite 사례를 제시했다. [출시 근거](https://www.furtherai.com/blog/furtherai-code-gen) | 031과 같은 근거 결함이 있어 별도 주장으로 두지 않고 **제외**한다. |

## 최종 정리

1. 30개 발견 기록 가운데 25개 기록이 12개 고객 대상 AI E2E 주장에 사용됐다.
2. 그중 13개는 별도 주장이 아니라 상위 워크플로우의 단계·채널·입력 변형으로 흡수됐다.
3. Portfolio Insights, Bordereaux, Code Gen 3개 기록은 AI와 해당 작업의 직접 연결이 없어 제외됐다.
