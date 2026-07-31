# Wordsmith AI 1차 주장 요약과 재검토

## 먼저 알아둘 점

이 문서는 기존 `work/wordsmith-ai/research.json`의 37개 발견 기록을 현재 1차 기준으로 다시 판정한 결과다. 새 자료를 조사한 것이 아니라, 저장된 출처와 인용만 사용해 C0·C1·A1·A2를 다시 적용하고 하위 기능을 상위 E2E 워크플로우에 병합했다.

현재 자료를 고객의 처음 요청부터 최종 결과까지 묶어 보면 다음과 같다.

- 최종 고객 대상 AI E2E 주장: 10개
- 상위 주장에 흡수된 하위 기록: 18개
- 별도 주장으로 통과하지 못한 기록: 9개

따라서 Wordsmith가 고객에게 제공한다고 직접 주장하는 AI 워크플로우 수는 현재 근거 기준 **10개**다. 모든 조사 범위를 이미 함께 본 상태이므로 근거가 부족한 기록은 더 이상 보류로 남기지 않고 제외했다.

## 2차 조사 전달 목록

2차 조사에는 아래 **10개 상위 E2E 주장만** 전달한다. 포함된 하위 ID는 해당 상위 주장의 단계·변형·추가 근거이며 별도 2차 조사 건으로 세지 않는다.

| 2차 기준 ID | 전달할 E2E 주장 | 함께 흡수된 기존 ID | 2차 전달 |
|---|---|---|---|
| 001 | 계약 검토·협상 | 017, 021, 025, 026, 032, 033 | 전달 |
| 002 | 법률 문서 작성 | 없음 | 전달 |
| 003 | 법률 문서 번역 | 없음 | 전달 |
| 004 | 근거 기반 법률 조사·답변 | 005, 009, 013 | 전달 |
| 006 | 법률 요청 접수·해결 | 007, 018, 019, 030 | 전달 |
| 008 | 계약 저장소 분석·모니터링 | 011, 015, 020, 034 | 전달 |
| 010 | 플레이북 생성 | 없음 | 전달 |
| 016 | 규제 변화 모니터링·대응 | 035 | 전달 |
| 027 | Data-room 실사 | 없음 | 전달 |
| 031 | KYC reconciliation | 없음 | 전달 |

다음 ID는 2차로 넘기지 않는다: `012`, `014`, `022`, `023`, `024`, `028`, `029`, `036`, `037`. 병합된 하위 ID 역시 독립 건으로는 넘기지 않는다.

## 전체 흐름으로 보면

| 상위 E2E 주장 | 포함되는 기존 기록 | 하나로 보는 이유 |
|---|---|---|
| 계약 검토·협상 | 001, 017, 021, 025, 026, 032, 033 | 계약과 기준을 받아 차이·위험을 판단하고 검토 결과와 redline을 내는 같은 핵심 업무의 산업별 변형 |
| 법률 문서 작성 | 002 | 업무 맥락과 형식을 받아 검토 가능한 법률 문서를 완성하는 흐름 |
| 법률 문서 번역 | 003 | 번역 자체가 별도로 요청되고 완성된 번역 문서로 끝나는 독립 업무 |
| 근거 기반 법률 조사·답변 | 004, 005, 009, 013 | 질문과 자료를 받아 근거가 달린 법률 답변을 돌려주는 같은 업무의 채널·접근 방식 변형 |
| 법률 요청 접수·해결 | 006, 007, 018, 019, 030 | 채널 요청을 처리하거나 사람에게 이관하고 기록하는 흐름. 조달·NDA는 구체적인 요청 유형 |
| 계약 저장소 분석·모니터링 | 008, 011, 015, 020, 034 | 저장된 문서를 구조화해 보고서·등록부·알림으로 계속 관리하는 하나의 저장소 운영 흐름 |
| 플레이북 생성 | 010 | 계약 템플릿에서 검토 기준을 만드는 독립 준비 업무 |
| 규제 변화 모니터링·대응 | 016, 035 | 규제나 scheme 변화를 감시해 영향과 후속 조치를 내는 같은 상위 업무 |
| Data-room 실사 | 027 | data room 전체를 체크리스트로 검토해 우선순위 보고서를 만드는 독립 업무 |
| KYC reconciliation | 031 | KYC pack을 점검해 누락표와 후속 이메일을 만드는 독립 업무 |

## 주장별 설명

표의 “경계 판단”은 기존에 왜 하나로 묶였는지와 새 방법에서는 어떻게 다룰지를 함께 설명한다.

| ID | 기존 주장과 입출력 | 왜 AI라고 가져왔나·핵심 근거 | 경계 판단과 현재 판정 |
|---|---|---|---|
| 001 계약 검토·redline | 계약과 플레이북 → 위험 설명, fallback, redline, 표시된 계약서 | 제품 페이지가 결과에 `AI reasoning`이 포함된다고 명시했다. [제품 근거](https://www.wordsmith.ai/products/review) | 계약 검토·협상의 **상위 E2E 주장으로 통과**한다. 추출·위험 판단·redline은 나누지 않고 단계로 두며, 017·021·025·026·032·033은 산업별 예시와 추가 근거로 병합한다. |
| 002 법률 문서 작성 | 이메일·양식·정책 등의 업무 맥락과 템플릿 → 검토 가능한 법률 문서 | Wordsmith가 AI로 계약·평가 초안을 자동화한다고 설명했다. [데모 근거](https://www.wordsmith.ai/demo/intelligent-drafting) | 작성 과정을 쪼개지 않고 **독립 E2E 주장으로 통과**한다. |
| 003 법률 문서 번역 | 법률 문서와 목표 언어 → 형식을 보존한 번역 문서 | 제품 페이지가 여러 `AI translation services`를 사용한다고 적었다. [제품 근거](https://www.wordsmith.ai/products/assistant) | 번역은 별도로 요청되고 번역 문서로 끝나므로 **독립 E2E 주장으로 통과**한다. |
| 004 인용 법률 조사 | 법률 질문·관할 → 법령 원문에 연결된 조사 보고서 | 제품 페이지가 LLM 답변의 원자료를 확인할 수 있다고 설명했다. [제품 근거](https://www.wordsmith.ai/products/assistant) | 근거 기반 법률 조사·답변의 **상위 E2E 주장으로 통과**한다. 검색·합성·인용은 내부 단계이고 005·009·013은 채널 또는 접근 방식의 변형으로 병합한다. |
| 005 채널 법률 Q&A | Slack·Teams 등의 직원 질문과 승인 지식 → 검토된 답변과 기록 | Wordsmith agent가 Slack 질문을 읽고 승인 지식을 확인해 답한다고 직접 설명했다. [제품 근거](https://www.wordsmith.ai/products/intake) | 질문 채널만 다르고 최종 목적이 근거 있는 답변이므로 **004에 병합**한다. 승인·전달·기록은 그 E2E의 단계다. |
| 006 법률 요청 운영 | 여러 채널의 요청·플레이북 → 일상 업무 해결 또는 변호사에게 정리된 이관 | 회사가 `AI workers`가 routine 업무를 해결한다고 적었다. [회사 발표](https://www.wordsmith.ai/blog/wordsmith-ai-raises-70-million-series-b) | 접수·분류·처리·이관·기록을 포함한 **상위 E2E 주장으로 통과**한다. 007·018·019·030은 채널이나 요청 유형의 사례로 편입한다. |
| 007 이메일 스레드 지원 | Outlook/Gmail 스레드와 플레이북 → 요약, 답장 초안 또는 계약검토 시작 | 통합 페이지가 inbox의 `AI associate`라고 직접 표현했다. [통합 근거](https://www.wordsmith.ai/integrations) | 이메일은 별도 업무라기보다 법률 요청의 유입 채널이다. 요약·답장·검토 시작을 쪼개지 않고 **006의 단계와 근거로 병합**한다. |
| 008 계약 생애주기 알림 | 연결된 체결 계약 → 갱신·마감·의무·위험 알림 | `The AI extracts` dates and obligations라는 직접 표현이 있다. [제품 근거](https://www.wordsmith.ai/products/repositories) | 계약 저장소 분석·모니터링의 **상위 E2E 주장으로 통과**한다. 추출·보고·알림을 하나의 지속 관리 흐름으로 보고 011·015·020·034를 병합한다. |
| 009 공개 문서 RAG | 로컬 문서와 질문 → 문서에 근거한 답변 | 공식 저장소가 `Retrieval-Augmented Generation (RAG)` 사용을 명시했다. [GitHub 근거](https://github.com/wordsmith-ai/hello-wordsmith) | 외부 사용자가 이용할 수 있는 공개 구현이지만 최종 목적은 같은 근거 기반 답변이므로 **004에 병합**한다. |
| 010 플레이북 Smart Import | 계약 템플릿 → 편집 가능한 첫 플레이북 | 제품 페이지가 `Wordsmith AI generates` the first version이라고 적었다. [제품 근거](https://www.wordsmith.ai/product/playbooks) | 별도로 실행하고 완성된 플레이북을 받으므로 **독립 E2E 주장으로 통과**한다. |
| 011 Smart Columns 추출 | 저장소 문서와 추출 지시 → 구조화 메타데이터 열 | Academy 자료가 `AI engine`이 파일을 검토하고 정보를 열에 저장한다고 설명했다. [교육 자료](https://academy.wordsmith.ai/en/public/resources/document-lifecycle-management-with-repositories-2026-02-06) | 구조화 열은 저장소 보고·알림을 만들기 위한 중간 결과로 보고 **008에 병합**한다. 별도 판매 업무라는 근거가 확인될 때만 독립시킨다. |
| 012 Jira·Calendar MCP 에이전트 | 트리거·Jira·Calendar → 우선순위 티켓과 예약된 회의 | 영상이 `AI agent`가 티켓을 triage하고 회의를 잡는다고 설명했다. [Academy 영상](https://academy.wordsmith.ai/public/videos/what-is-mcp-2026-02-15) | 일반 제작 튜토리얼이며 Wordsmith 고객 법률제품으로 제공된 근거가 없어 `no_customer_delivery`로 **제외**한다. |
| 013 Legal Insights API | 인증 API 질문·문서 → AI 법률 답변과 첨부물 | API 문서가 `AI-powered legal insights`를 반환한다고 명시했다. [API 근거](https://docs.wordsmith.ai/introduction) | API는 같은 법률 조사·답변 업무의 접근 방식이므로 **004에 병합**한다. 첨부물도 한 요청의 최종 답변 묶음으로 본다. |
| 014 파일 질의·비교 | 법률 파일과 질문 → 답변, 조항 비교 또는 의무 요약 | 기존 근거는 일반 `AI capabilities` 문장 뒤에 파일 기능을 이어 붙였다. [블로그 근거](https://www.wordsmith.ai/blog/best-ai-legal-tools-software) | AI와 해당 작업을 같은 문장에서 직접 연결하지 못하므로 `no_ai_attribution`으로 **제외**한다. |
| 015 다계약 보고서 | 계약 묶음과 질문 → 출처가 달린 구조화 보고서 | 인터뷰가 machine-learning extractor와 여러 LLM layer를 직접 설명했다. [인터뷰 근거](https://www.artificiallawyer.com/2025/01/22/wordsmith-ai-launches-doc-review-reports/) | 여러 계약을 추출·분석해 보고하는 과정 전체를 나누지 않고 **008 저장소 분석 E2E에 병합**한다. |
| 016 규제 horizon scanning | 관할·주제·회사 맥락 → 행동이 필요한 규제 알림 | 공식 글이 `Horizon-scanning Agents`가 변화를 감시하고 알린다고 명시했다. [공식 근거](https://www.wordsmith.ai/blog/how-financial-services-legal-teams-can-deploy-ai-agents-that-hold-up-under-scrutiny) | 규제 변화 감지부터 회사별 알림과 후속 대응까지의 **상위 E2E 주장으로 통과**하고 035를 결제 분야의 사례로 병합한다. |
| 017 계약 규제준수 개선 | 계약 포트폴리오·DORA 테스트 → gap, 우선순위, addendum·통지 | `A Wordsmith Agent`가 조항별 상태와 인용을 돌려준다고 적었다. [금융 에이전트 근거](https://www.wordsmith.ai/blog/wordsmith-for-financial-services-three-agents-built-for-the-work) | 규제 기준으로 계약을 검토하고 개선하는 산업별 변형이므로 상태 판정·문서 초안을 쪼개지 않고 **001에 병합**한다. |
| 018 조달 벤더 계약 처리 | 조달 inbox 계약과 플레이북 → redline, 회신, 공급자 등록부 갱신 | 회사가 `Wordsmith Agents are AI workers`라고 한 뒤 같은 흐름을 설명했다. [공식 근거](https://www.wordsmith.ai/blog/in-house-legal-upgraded) | 법률 요청 운영이 처리하는 조달 요청 사례이므로 검토·redline·회신·기록을 함께 **006에 병합**한다. |
| 019 NDA 요청 처리 | Slack NDA 요청·상대방 정보·템플릿 → 서명용 NDA와 기록 | 같은 공식 글에서 AI worker가 템플릿을 채우고 서명으로 보낸다고 설명했다. [공식 근거](https://www.wordsmith.ai/blog/in-house-legal-upgraded) | NDA는 법률 요청 운영이 해결하는 구체 요청 유형이다. 작성·승인·전송을 나누지 않고 **006의 대표 사례로 병합**한다. |
| 020 ROPA 보고서 | DPA·설문·정책 저장소 → 지속 갱신되는 vendor별 ROPA | 공식 출시 글이 `With AI`와 Wordsmith ROPA의 추출·행 구성을 연결했다. [출시 근거](https://www.wordsmith.ai/blog/introducing-the-new-ropa-report-in-wordsmith) | 저장소 자료를 구조화하고 지속 갱신하는 같은 운영 목적이므로 **008에 병합**한다. ROPA는 그 E2E의 구체 최종 보고서다. |
| 021 고용계약 감사 | 체결 고용계약과 표준조건 → gap 보고서, redline, 직원 통지 | 공식 글이 `The AI extracts` 핵심 조건을 구조화 보고서로 만든다고 적었다. [HR 근거](https://www.wordsmith.ai/blog/legal-hr) | 고용계약이라는 도메인만 다를 뿐 기준 비교와 개선 문서가 한 계약 검토 결과이므로 **001에 병합**한다. |
| 022 설문서 작성 | 과거 승인 답변과 새 RFP·보안·개인정보 설문 → 인용된 완성 설문 | 공식 글이 Wordsmith가 과거 답변으로 학습하고 새 답을 쓴다고 설명했다. [보안 근거](https://www.wordsmith.ai/blog/legal-security) | `trains`라는 표현만으로는 해당 작업을 모델·LLM·agent에 직접 귀속하지 못하므로 `no_ai_attribution`으로 **제외**한다. |
| 023 법률 시나리오 계산 | 계약·term sheet·cap table·손해 입력 → 비용·노출·시나리오 계산 | 공식 글이 실제 Wordsmith use case와 OpenAI `o1`의 수치 모델링 개선을 연결했다. [기술 블로그](https://www.wordsmith.ai/blog/lessons-from-openai-s-o1-model-implications-for-wordsmith-and-legal-ai) | Wordsmith 계산 작업과 `o1` 설명이 서로 다른 문장에 있어 직접 귀속으로 볼 수 없으므로 **제외**한다. |
| 024 Office 파일 생성 | 메모·이사회 업데이트와 스타일 → 문서·슬라이드 파일 | 기존 인용은 Wordsmith Computer가 파일을 만든다는 설명과 일반 AI 한계를 넓게 묶었다. [공식 글](https://www.wordsmith.ai/blog/legal-workflow-management-requires-more-than-a-chatbot) | AI 문장과 파일 생성 문장이 분리돼 있어 직접 AI 근거가 없으므로 **제외**한다. |
| 025 Side-letter MFN 검토 | 새 side letter·LPA·기존 약정 → MFN 표, 검토 항목, 통지 초안 | 공식 글이 agent가 문서를 읽고 단일 표를 만든다고 설명했다. [사모펀드 근거](https://www.wordsmith.ai/blog/private-capital-three-agents-built-for-the-fund-lifecycle) | MFN 추출·권리판정·통지초안 전체를 쪼개지 않고 사모펀드용 계약 검토 변형으로 **001에 병합**한다. |
| 026 사모계약 적합성 검토 | 투자계약과 플레이북·선례 → 조항별 보고, redline, 이관 | 같은 글이 agent의 playbook 검토와 결과를 설명했다. [사모펀드 근거](https://www.wordsmith.ai/blog/private-capital-three-agents-built-for-the-fund-lifecycle) | 비교·redline·이관은 한 검토 결과 패키지다. 산업별 예시로 **001에 병합**한다. |
| 027 Data-room 실사 | data room과 체크리스트 → 출처가 달린 우선순위 실사 보고서 | 공식 글이 agent가 data room을 체크리스트로 검토한다고 적었다. [사모펀드 근거](https://www.wordsmith.ai/blog/private-capital-three-agents-built-for-the-fund-lifecycle) | 별도 요청되고 실사 보고서로 끝나므로 **독립 E2E 주장으로 통과**한다. 색인·위험 추출·우선순위는 내부 단계다. |
| 028 사내 Slack AI 코딩 | Slack 개발 작업 → PR·스크린샷·데모 | 글에 AI가 코드를 쓴다는 설명은 있다. [엔지니어링 근거](https://www.wordsmith.ai/blog/what-it-actually-looks-like-to-build-an-ai-native-legal-tech-company) | Wordsmith 개발팀의 사내 업무이지 고객 법률 제품이 아니다. `internal_workflow`로 **제외**한다. |
| 029 Implicit Memories | 반복 사용자 행동 → 이후 업무에 반영된 선호 | 글이 일반 AI와 Wordsmith 기억 기능을 비교한다. [기능 근거](https://www.wordsmith.ai/blog/why-your-legal-ai-should-remember-how-you-think) | 외부 사용자가 받는 독립 산출물이 아니라 여러 업무에 쓰이는 제품 속성이므로 `not_workflow`로 **제외**한다. |
| 030 법률 업무 reconciliation | 요청·의무·비용·결정 기록 → 예상과 실제 업무 비교 | `AI workers`가 routine 업무를 처리하고 실제 결과를 대조한다고 직접 설명했다. [회사 발표](https://www.wordsmith.ai/blog/wordsmith-ai-raises-70-million-series-b) | 별도 주장으로 늘리지 않고 **006 법률 요청 운영의 사후 기록·비교 단계로 병합**한다. |
| 031 KYC reconciliation | KYC pack·체크리스트·과거 증빙 → 출처별 완결성 표와 누락 이메일 | 공식 글이 `A Wordsmith Agent`가 문서를 체크리스트와 대조한다고 적었다. [금융 에이전트 근거](https://www.wordsmith.ai/blog/wordsmith-for-financial-services-three-agents-built-for-the-work) | 별도 요청에서 완결성 표와 후속 이메일까지 끝나므로 **독립 E2E 주장으로 통과**한다. 대조와 이메일 작성은 단계다. |
| 032 Term sheet 대 계약 gap | 승인 term sheet와 계약 초안 → 이중 인용 discrepancy 표와 redline | 공식 글이 `A Wordsmith Agent`가 두 문서를 비교한다고 설명했다. [금융 에이전트 근거](https://www.wordsmith.ai/blog/wordsmith-for-financial-services-three-agents-built-for-the-work) | term sheet 비교는 계약 검토의 금융권 변형이다. 매핑·비교·redline을 나누지 않고 **001에 병합**한다. |
| 033 Merchant 계약 검토 | merchant 계약·playbook·카드사 필수조항 → 표시 계약, 노출평가, 협상노트 | 결제용 AI Agent 글에서 agent가 조항을 평가하고 필수조항을 검사한다고 적었다. [결제 에이전트 근거](https://www.wordsmith.ai/blog/wordsmith-for-payments-three-agents-built-for-the-work) | merchant 계약이라는 도메인만 다르고 최종 목적이 계약 검토·협상이므로 **001에 병합**한다. |
| 034 Sponsor-bank 의무 등록부 | 은행 계약의 여러 의무 → live register와 attestations | 같은 공식 글이 agent가 계약을 읽어 의무 목록과 증빙기한을 만든다고 설명했다. [결제 에이전트 근거](https://www.wordsmith.ai/blog/wordsmith-for-payments-three-agents-built-for-the-work) | 의무 추출·담당자 배정·증빙 작성·갱신을 쪼개지 않고 **008 저장소 분석·모니터링에 병합**한다. |
| 035 Scheme bulletin 대응 | Visa·Mastercard bulletin과 회사 규칙 → 정책·계약·고객 통지 초안과 처리기록 | 공식 글이 agent가 관련 변경을 골라 각 문서를 작성한다고 설명했다. [결제 에이전트 근거](https://www.wordsmith.ai/blog/wordsmith-for-payments-three-agents-built-for-the-work) | 규제 변화를 감시해 영향을 판단하고 후속 문서를 만드는 흐름이므로 **016 규제 모니터링·대응에 병합**한다. |
| 036 미디어 권리 확인 | 권리 계약과 인수 IP 계약 → 독점·판매가능·clearance 판단 | 고객 사례는 Wordsmith 검토를 말하지만 AI 표현은 “AI-driven checks could”라는 미래 전망이었다. [고객 사례](https://www.wordsmith.ai/customers-stories/animaj) | 현재 실제 작업을 AI에 직접 귀속하지 못한다. `no_ai_attribution`으로 **제외**한다. |
| 037 영업계약 라우팅 | 새 영업계약 → 체결 계약의 저장 | AI-powered 자동화라는 일반 문구와 가상의 “could create” 흐름을 사용했다. [일반 글](https://www.wordsmith.ai/articles/contract-management-automation-how-ai-streamlines-legal-workflows) | Wordsmith 제품의 실제 고객 워크플로라는 근거도, 정확한 AI 작업 근거도 부족하다. **제외**한다. |

## 최종 정리

1. 37개 발견 기록 가운데 28개 기록이 10개 고객 대상 AI E2E 주장에 사용됐다.
2. 그중 18개는 별도 주장이 아니라 상위 워크플로우의 단계·채널·산업별 사례로 흡수됐다.
3. 나머지 9개는 고객 제공, 직접 AI 귀속, 또는 독립 워크플로우 요건을 충족하지 못해 제외됐다.
