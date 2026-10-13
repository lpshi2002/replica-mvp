# 진행자 추가 근거 — 2026-10-13

## 현재 비용 구조

browser-cost-profile.json은 최신 채택된3개 평가의 events.jsonl과 tester_call_id별 영수증을 연결한 읽기 전용 집계다. 재실행을 포함하지 않는다. 기존 실행은 O3 이전이며 모델도 Sonnet/Opus가 섞여 있어 새 A/B 기준으로 그대로 쓰면 안 된다.

| 모델이 선택한 행동 | 호출 수 | CLI 추정액 |
|---|---:|---:|
| click | 197 | $4.0291 |
| fill | 82 | $1.6029 |
| wait_for | 48 | $0.8677 |
| wait | 23 | $0.6596 |
| done | 21 | $0.5167 |
| upload | 16 | $0.2632 |
| check | 11 | $0.2057 |
| select | 2 | $0.0375 |
| read | 1 | $0.0261 |

wait_for 내부의 polling은 이미 코드로 처리된다. 71건은 대기를 선택하는 모델 호출 수이며 polling횟수가 아니다. 화면에 나타난 pending상태의 완료조건을 안전하게 실행기에서 처리하면 없앨 여지가 있으나, 71건 전부 제거 가능하다는 뜻은 아니다. 입력→제출→pending 관측→대기→결과 관측을 한 작업으로 다룰 후보와, 결과를 읽어 다음 입력을 바꿔야 하는 단계를 구별할 가치가 있다.

반복된 label은 Send16, Knowledge11, Visitor chat11, Contacts11, Add contact9 등이다. 같은 label이라고 같은 절차/동일DOM/같은부작용이라고 보장하지 않는다. 학습한 조작 절차를 같은 앱의 여러 사례에서 재사용할 가능성을 따져볼 근거일 뿐이다.

전체 최종 채택 평가 $13.702076 중 tester $8.208604, 나머지 $5.493472다. 다른 단계를 그대로 두면 tester50% 절감은 전체29.95%, tester75%절감은 전체44.93%다. 전체50%를 tester만으로 줄이려면 tester 비용을 약83.46% 줄여야 한다. 이는 목표를 판단하는 산술이지 예상 효과가 아니다.

## 1차 문서에서 확인한 설계 패턴

- [Stagehand speed optimization](https://docs.stagehand.dev/v3/best-practices/speed-optimization): 한 번 observe로 여러 폼 행동을 계획하고 액션 객체로 실행하면 이후 동작에 LLM을 다시 부르지 않는 패턴을 설명한다. 공급자 속도배수는 이 프로젝트 비용 절감 근거로 쓰지 않는다.
- [Stagehand action caching](https://docs.stagehand.dev/v3/best-practices/caching): 조작 계획의 캐시와 변수 바인딩, 페이지/URL/옵션에 따른 무효화를 설명한다. 실제 결과/판정 캐시가 아니다. 가변 입력마다 탐색을 반복하지 않는 방향의 참고이며, 외부 프레임워크 도입을 권고한 것은 아니다.
- [Browser Use parameters](https://docs.browser-use.com/open-source/customize/agent/all-parameters): max_actions_per_step과 화면 변경 시 중단, initial_actions, vision제어를 제공한다. 문서/버전별 기본값 차이가 있으므로 숫자 자체를 설계 근거로 삼지 않는다. flash_mode는 생각·평가를 생략하므로 판정 품질 유지의 자동 해법이 아니다.
- [Playwright auto-wait](https://playwright.dev/docs/actionability): 가시성/활성화/안정성 등 행동 가능성을 코드로 확인한다. 앱의 의미적 성공을 판정하는 기능은 아니다. [locators](https://playwright.dev/docs/locators)는 매 행동 때 현재DOM을 다시 찾으므로 이전노드와같음은별도검증이필요하다.

외부 문서의 DOM삭제·iframe제거·리소스차단 예시는 이 평가에 그대로 적용하면 시험 대상을 바꾸므로 채택 근거에서 제외한다. 원본 관측/화면/동작은 보존하고 전송 표현만 줄인다.

## 중요한 설계 경계

현재 모델 호출은 매번 임시cwd의 독립CLI이며 --no-session-persistence를 사용한다. 따라서 "변경점만 보내기"는 이전 상태가 어디에 남는지 먼저 해결해야 한다. 이전 화면을 알 수 없는 모델에 delta만 보내거나, 보이지 않는 결과를 기존 값으로 채우면 안 된다. 새 상태 유지 세션은 문맥 증가·캐시·격리 비용을 함께 검증해야 한다.

절차 캐시의 첫 생성/탐색 비용도 회사의 한 번 평가 총비용에 넣는다. 여러 번 돌려서 나중에 싸지는 효과로 최초기업평가가싸졌다고 보고하지 않는다. 실제 브라우저 행동/관측은 매번 수행하고 새로운입력·신규결과를검증한다. 구현자가 만든 성공스크립트를 독립최종시험으로 그대로 채택하지 않는다.

## 전송 내용의 구성

prompt-component-profile.json은 관측이 보존된323개 호출에 현재O3 프롬프트 함수를 적용한 UTF-8 크기다. 전체2,725,379바이트 중 page값1,216,710(약44.6%), previous_actions582,739(약21.4%), 고정instruction+actions492,898(약18.1%), case382,914(약14.0%)다. 키·구분자는 별도라합계차이가있다. 토큰/비용비중이 아니며 claim003은관측이없어제외했다. 이는 화면전송과반복된고정본문을검토할근거이지, 그내용을그대로삭제할수있다는뜻이아니다.

## 追加비교와 반론 질문

[Stagehand deterministic scripts](https://docs.stagehand.dev/v3/best-practices/deterministic-agent)는 첫 실행에 에이전트 탐색 비용을 쓰고 이후 실행에서 저장한 조작을 수행한다고 명시한다. 후속 실행의 0토큰을 최초 기업 평가 비용으로 가져오면 안 된다. 같은 회사 평가의 여러 사례 안에서 준비비를 회수할 수 있는지 별도로 검증한다.

[microsoft/playwright-cli](https://github.com/microsoft/playwright-cli)의 코드 실행·기록/선택자 도구도 참고 후보지만, 현재 런너는 이미 로컬 Playwright API를 직접 쓰고 모델에는 --tools ""로 호출한다. 단순 MCP→CLI 교체 절감을 다시 적용했다고 할 근거는 없다.

큰 구조안을 검토할 때 “새 화면마다 무조건 모델”과 “임의의 전체 작업을 눈감고 재생” 사이도 비교해야 한다. 이미 학습·검증한 메뉴→폼 절차는 매 원자 행동 후 실제 새 화면을 관측하고 다음 단계의 사전조건을 코드로 대조할 수 있다. 이를 만족할 때의 절차 재사용과, 새 응답을 이해해야 하는 의미적 분기에서의 모델 복귀를 구분할 필요가 있다. 특정 화면이관측됐다/label이있다는것만으로 절차의정확성이 입증되는 것은 아니다.

새 절차를 선택할 때마다 별도의 router/plan 모델을 부르지 않도록, 원래 tester 판단이 절차 생성·선택을 함께 맡을 수 있는지 구체화하라. 준비비·카탈로그 추가 문맥·검증·fallback도 비용에 넣는다. 값 바인딩은 이번 사례의 입력을 사용하며 동적 입력에 따라 분기가 바뀌면 재사용을 멈춘다.

## 002 검토 뒤 독립 확인과 정정 요구

cache-and-candidate-check.json은 같은 receipts를 역할/모델로 합산했다. tester/Judge/code_review의 1h cache-write 귀속액은 총 $10.881288 (기존 CLI의 모델별 역산 쓰기단가 적용)이다. 토큰 배정과 호출이 그대로이고 쓰기 배수만2→1.25라면 $4.080483 감소, 전체13.702076의 약29.78%라는 조건부 계산이 된다. 실측 절감/현재 API요금/실청구가 아니다. 캐시를 끄면 read토큰도정가가되므로 쓰기비절반만 절감이라고 하면 안 된다.

고정된 cache-read토큰 수만으로 읽힌 내용이나 모든 동적부분이 다시읽히지않음을 특정할 수 없다. cwd원인은가설이다. 설치CLI help의 --exclude-dynamic-system-prompt-sections(기본시스템프롬프트에서머신별cwd등을 user메시지로이동)은 공유cwd보다먼저검토할후보이나 영향실측이필요하다. 새로운회사자료/사례/화면데이터를 --append-system-prompt로승격하면신뢰경계와입력계약이바뀌므로기각한다. 필요시고정된신뢰가능tester지침만별도검토한다. TTL만바꾸는것과cwd/메시지역할변경은검증범위가같지않다.

71wait + post-input99를 '42% 상한'이라한것은성립하지않는다. 조건정의따라수치가달라지고 다른절차최적화는포함하지않으며, 안전흡수검증도없다. 진행자의더엄격한동일case·연속URL조건은97개,wait와중복0,합168/$3.4255604다. 이는후보목록일뿐상한/실제절감아님. 모델·문맥길이다르므로콜수비례로요금을추정하지말고 실제call_id별비용에서계획출력·폴백을반영한다.

B1이원자행동을보존한다면 history항목수가자동으로줄지는않는다. 줄어드는것은모델호출기회다. S3의유일role/name만으로같은노드임을보장하지못한다. 한계획내실제nodeidentity를확인하고동일이름의교체노드는중단해야한다. 후속사례의절차재사용은다시관측·결합하고버전/전후조건검증이필요하다.

B2의첫기업평가회수효과는입증되지않았지만 '거의적용안됨'도입증되지않았다. 별도학습회차없음,첫실제사례의절차와후속사례반복부분재사용으로범위를제한한실험안을비교한뒤조건부보류가능. O9는CLI num_turns2를추가LLM1회라고오독하는쟁점이며401calls의usage.iterations는각1message여서2회를1회로줄인다는절감계산은기각한다.

공식 Claude Code [prompt caching](https://code.claude.com/docs/en/prompt-caching)도 디렉터리별시스템정보가접두부재사용에영향을준다고설명한다. 이는cwd가설의설계근거이나이실행의miss구간을추적한실측은아니다. 설치 --help에서 exclude-dynamic-system-prompt-sections를재확인했다. TTL은자식프로세스의CLAUDE_CODE_PROMPT_CACHE_TTL로명시하고 실제usage.cache_creation의5m/1h계수를기록한다. 전역설정변경이나사례데이터system승격은권고하지않는다. 과금형태에따라기본TTL이달라지므로과거의1h영수증을현재전체실행의기본값으로일반화하지않는다.
