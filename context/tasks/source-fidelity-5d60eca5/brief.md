# 조사 출처를 효율적이고 정확하게 가져오는 방법

## 사용자 요청 (2026-10-16, 원문)

> 음 최대한 효율적으로 정확한 정보를 가져올수있게끔 하는 방법을 코덱스랑 토론해서 생각해봐 전문가가 쓸법한 로직을 통해서 생각해내고 어느 한 무언가에 매몰되지않게 근거있는 내용을 가지고 판단해서 결론을 내봐

같은 대화의 직전 발언(의도 확인용):

> 아니 사실 그게 있냐 없냐 뭐 그런게 중요한게 아니라 의미가 달라지는게 사실 제일 큰문젠데 그게 안고쳐지는거는 필요가 없지

> 애초에 지금 1차에서 가져올때 정확하게 가져오도록 하면 되는거잖아 지금 뭐 요약을 해서 가져오나?

> ralph도 외부 검색을 하는걸로 알고있는데 얘네는 어떻게 처리함?

## 범위

- 대상: Replica 1차·2차 조사(`skills/replica-research/SKILL.md`, `agents/replica-first-pass.md`, `agents/replica-second-pass.md`)가 공개 출처에서 사실·조건·인용을 가져오는 과정, 그리고 그 인용이 시험 기준(demo plan 기대 결과, `boundaries`)이 되기까지.
- 목표: **의미가 바뀌지 않은 정확한 정보**를 **최소 비용·시간**으로 확보하는 방법. 사용자 기준으로 "인용이 원문에 존재하는가"는 그 자체로 목표가 아니며, 의미가 바뀌는 문제를 해결하지 못하는 장치는 불필요하다.
- 토론만 요청됨. 제품 코드·지침·방향 문서는 수정하지 않는다.

## 확정된 제약 (project-direction.md)

- 기업 입력 이후 사람 개입 없이 자동 완료. 사람 검토를 완료 조건으로 둘 수 없다.
- 현재 우선순위(2026-10-15): 보고서·질문 생성 보류, 복제품 구현·사용·시험 우선.
- 시험 기준은 구현 전에 고정하고 구현을 본 뒤 바꾸지 않는다. 원제품 접근이 불가하거나 기능이 폐지된 경우가 많아 공개 문서가 사실상 정답 기준이 된다.

## 진행자가 이번 대화에서 확인한 사실 (근거)

1. **v4 출처 원문 대조** (2026-10-16, 진행자 실행): `work/delphi-ai-v4/research.json`의 URL–발췌 148쌍(1차 12, 2차 136)을 현재 페이지와 문자열 비교. 약 125 일치(공백·문장부호 정규화 후), 서식 차이 5, 떨어진 두 문장 이어붙이기 2(Karamo 블로그, Tavus 사례 — 1차), 단어 누락 2("continue … **or** start a new one"의 or, arXiv의 the), 현재 페이지에 없음 1(Twilio, 페이지 변경 가능), 확인 불가 13(404·403·JS 렌더·로그인). 시험 기준이 된 Interviewer 진행률·100% 관련 발췌는 일치. 스크립트·결과: `/private/tmp/claude-501/-Users-cho-replica-mvp/90c76e30-19bb-4abb-b668-44a2175fa6e8/scratchpad/check.py`, `fuzzy.py`, `results.json`. 한계: 오늘 페이지 기준, 단순 HTML 제거.
2. **v4의 실제 치명 오류는 해석**: Interviewer `completion-new-topic`이 "6번의 자세한 답변 안에 100%가 안 되면 실패"를 `public_rule`로 분류. 같은 2차 결과의 `boundaries`는 "how many answers reach 100%"가 공개되지 않았다고 적음(`work/delphi-ai-v4/second_pass/creator-interview-to-mind-snippets.json:78`). 구현자가 이 상한에 맞춰 점수를 올림(`tmp/reviews/delphi-v4-postrun-review-2026-10-12.md` 4절).
3. **가져오는 도구**: v4 2차 작업자 6개 세션 기록(`~/.claude/projects/-Users-cho-replica-mvp/e791593d-b92f-4b1d-92ce-cad9e8f91720/subagents/agent-*.jsonl`)에서 WebFetch 3~11회, `curl` 10~18회, WebSearch 3~9회를 섞어 사용. WebFetch는 작은 모델이 프롬프트("Quote verbatim …")에 답한 결과를 돌려주므로 원문 보장이 없음. 1차 작업자의 도구 사용은 이 세션에서 확인하지 못함. 지침에는 이미 "verbatim, never paraphrase or join"이 있음(`replica-first-pass.md:47`).
4. **현재 검사 범위**: 인용이 *작성자가 기록한 발췌* 안에 있는지만 확인(`src/replica_mvp/project.py:449`, `src/replica_mvp/web_contract.py:49`). `f48374e`(2026-10-16)가 근거 유형 정의, 혼합 기준 분리, 실행 한도 예시를 지침에 추가(`replica-second-pass.md:305-322`) — 같은 에이전트의 자기 점검.
5. **Ralph-to-Ralph** (`namuh-eng/ralph-to-ralph` `b756d3d`, 읽기만 함): 조사 전 `scripts/scrape-docs.py`가 대상 문서 사이트를 결정적으로 수집(llms-full.txt → llms.txt → mint.json → OpenAPI → sitemap → BFS; Scrapling Fetcher → Stealthy → Playwright; trafilatura로 마크다운; 파일마다 `<!-- Source: URL -->`; 최소 20페이지 관문). 에이전트의 직접 스크래핑 금지(`ralph/inspect-prompt.md:36,50`). 웹 검색 지시는 프롬프트에서 찾지 못함. 인용 검증 장치 없음, 에이전트가 요약한 `docs-extract.md`를 넘김. 대신 원제품을 정답으로 QA하므로 문서 오독이 원제품 관찰로 드러남. Replica 출처는 블로그·도움말·기사·GitHub·보관본 등 분산.
6. **참고 연구**: `docs/replica-roadmap.md:128` Cited but Not Verified (arXiv 2605.06635) — 링크 작동 → 주제 관련성 → 사실 일치 세 층, 사실 일치에서만 잡히는 실패가 큼. 로드맵 단계 5(출처 스냅샷과 재확인)는 미구현. `exa-results/claim-reverse-engineering-2026-09-28.md` 5절에 VeriScore·AVeriTeC 등.
7. **규모**: v4 기능별 출처 인용 기대 결과 21/26/18개, 고유 페이지 8/8/3개. 최종 평가 판정 모델 63회 약 $6.33, 브라우저 테스터 1,111회.

## 해결할 질문

1. 의미 변경이 생기는 지점은 어디들인가(수집 도구, 발췌 선택·절단, 해석·기준화, 시간에 따른 페이지 변경 등)와 각각의 실제 빈도·영향은?
2. 각 지점에 맞는 가장 효율적인 장치는 무엇인가? 예방(수집 단계)과 탐지(고정 전 검사) 중 무엇을 어디에 둘지, 전문가 방법론(예: 사실 확인 실무, 체계적 문헌고찰의 이중 추출, 법률·규제 인용 관행, claim decomposition 기반 검증 연구 등)에서 근거 있는 것.
3. 검사 비용을 어디에 집중할 것인가(모든 출처 vs 시험 기준이 되는 인용만 등). 자동화 제약 아래 LLM 검증의 오류를 어떻게 측정·제어할 것인가.
4. 최소 구성으로 먼저 무엇을 넣고, 무엇은 효과가 확인될 때까지 미루는가.

## 완료 기준

- 위 질문마다 근거(이 저장소 자료, v4 실측, 외부 연구·실무)와 함께 판단이 있다.
- 단일 방법에 매몰되지 않도록 대안을 비교하고, 기각 이유와 재검토 조건이 있다.
- 권장 구성은 비용·효과·자동화 제약을 함께 고려한 우선순위로 제시한다.
- 사실·추론·미검증 가정을 구분한다.
