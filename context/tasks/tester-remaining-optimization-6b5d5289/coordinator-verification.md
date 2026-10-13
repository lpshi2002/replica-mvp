# 진행자 추가 검증 — 2026-10-12

## O6: 프롬프트 위치보다 먼저 비교할 CLI 경계 후보

현재 `model_calls.py:_model_command`는 `claude -p --safe-mode --no-session-persistence --tools "" --output-format json --json-schema ...`로 호출한다. `run_model_cli`는 호출마다 `TemporaryDirectory(prefix="replica-model-call-")`를 만들고 cwd로 넘긴다. 고정 지침·actions는 이미 `_tester_prompt` JSON 앞부분에 있다. 따라서 텍스트 순서를 단순히 앞쪽으로 옮기는 것은 신규 최적화가 아니다.

설치된 Claude Code 버전은 **2.1.296**이다. 2026-10-12 `claude --help`에서:
- `--exclude-dynamic-system-prompt-sections`: cwd, env info, memory paths, git status 등 기계별 문맥을 system에서 첫 user message로 이동. default system prompt에만 적용하고 `--system-prompt`에는 무시됨.
- `--append-system-prompt`: 기본 system에 추가. 경계·요금 개선은 도움말만으로 입증되지 않음.
- `--safe-mode`: 사용자 정의 설정/CLAUDE.md/skills 등을 비활성화하지만 인증과 모델 선택 등은 유지.
- `--bare`: API key 또는 명시적인 apiKeyHelper 경로이며 OAuth/keychain을 읽지 않는다고 명시됨. 현재 인증을 유지하는 단순 최적화 대체재로 추천할 수 없음.

**가설:** 매 호출 달라지는 cwd가 기본 system prefix 재사용을 방해한다면 exclude flag가 가장 작은 O6 실험 후보일 수 있다. 이 flag와 safe-mode의 실제 조합, 현재 backend cache 경계, 절감은 유료 실행하지 않아 미검증이다. 기본 지침을 교체하거나 공유 작업 디렉터리를 도입할 필요는 없다. case/facts/page의 지시 권한을 올리지 않는다.

[공식 CLI 문서](https://code.claude.com/docs/en/cli-reference)는 append와 exclude-dynamic flag를 설명한다. [공식 캐시 문서](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)는 캐시가 tools→system→messages의 prefix에 적용되고 해당 구간이 일치해야 한다고 설명한다. 이 API 규칙만으로 Claude Code의 경계를 단정하지 않는다. 조회만 수행했고 모델 평가나 계정 설정 변경은 하지 않았다.

## O1 / O7에서 유지할 검증 한계

이전 95/401은 같은 URL의 인접 패턴이다. 과거 이벤트와 페이지 관측에는 form 소속/실제 DOM 노드 동일성/가시성 변경을 재구성할 충분한 정보가 없어 안전한 절감 가능 호출 수로 확정할 수 없다. 현재 `_OBSERVE_SCRIPT`는 매번 ref를 삭제하고 다시 번호를 붙인다. 중간 관측을 그대로 재사용하면 잘못된 요소를 클릭할 수 있다.

입력만 묶으면 모델 호출이 줄 수 있지만, 앱 출력에 의존해 다음 질문을 만드는 대화에는 새 관측·모델 판단이 필요하다. 브라우저 자체를 제거하거나 backend만 검사하면 사용자가 확정한 동일 화면/실제 워크플로 검증 조건을 충족하지 않는다.

## 추가 관측: 모델 선택과 CLI 턴 수

위 세 최종 실행의 `receipts/*/{start.json,stdout.raw}`를 `phase=tester`로 묶어 재집계했다.

| claim | tester 호출 | 실제 모델 | envelope num_turns |
|---|---:|---|---|
| 001 | 138 | claude-sonnet-5-5 | 138개 모두 2 |
| 002 | 185 | claude-sonnet-5-5 | 185개 모두 2 |
| 003 | 78 | claude-opus-5-5 | 78개 모두 2 |

- O5/운영: 역할별 모델 지정 기능은 있지만 역사상 모든 claim이 저렴한 tester로 돌았던 것은 아니다. 현재 `model=None`이면 CLI 기본값을 사용한다. 기존에 채택한 저렴한 테스터 선택을 새 실행에서 명시·기록하는 운영 점검은 새 라우터 없이 가능하다. 과거 모델 차이를 O1/O6의 효과로 계산하지 않는다.
- 신규 관측 O9 후보: 우리 호출 수401은 CLI 실행 횟수다. `num_turns=2`를 곧바로 실제 API 호출802회 또는 비용50%낭비라고 해석할 수 없다. 구조화 출력 과정이 추가 턴을 만드는지 확인할 이유는 있으나 이번에는 내부 요청 추적을 하지 않았다. 일반 텍스트 JSON+로컬 검증으로 바꾸면 스키마 준수/재시도 비용이 달라질 수 있으므로 근거 없이 `--json-schema`를 제거하지 않는다. 필요성을 검토하고 중요하지 않으면 후순위로 둔다.
- O4: 최종 기대조건 35+29+21=85개 모두 `method=judge`이며 Judge 호출은 10+7+5=22회다. 기대조건 하나를 코드 검사로 옮겨도 같은 사례에 의미 조건이 남으면 Judge 호출은 유지된다. 실제 발송·외부 결과 증거를 파일 존재만으로 대체하면 안 된다.

## O8 지원 경로 확인과 002 검토의 수정 필요점

[공식 Claude Code 캐시 문서](https://code.claude.com/docs/en/prompt-caching#choose-the-ttl-yourself), [공식 환경변수](https://code.claude.com/docs/en/env-vars)를 2026-10-12 조회했다. `CLAUDE_CODE_PROMPT_CACHE_TTL=5m|1h`는 `-p`에 적용하고2.1.242이상에서 지원한다. `DISABLE_PROMPT_CACHING=1`도 문서에 있다. 현재2.1.296은명시된최소버전이상이다. 전역계정/셸설정을바꾸지않고 tester 자식process env에만 적용하는 실험이 가능하다는 근거이며, 실제작동/절감은확인하지않았다. `--bare`로인증을바꾸거나새API공급자를도입할필요없다.

002 Claude 표본427개를 독립재집계한 결과는 coordinator-cache-evidence.json이다. claim001 attempt002의164개와claim003의78개는Opus, claim002185개는Sonnet이었다. 427건의$7.15·87%·TTL절감비율은 모두Sonnet단가를쓴것이므로실제혼합실행의경제성근거로사용하지않는다. 최신표본401개와다른실행인점도명시해야한다.

일정한cache_read1977/1995만으로고정system만재사용하고사용자본문은한번도읽히지않았다고확정할수없다. envelope num_turns=2인호출내의캐시이용을아직분리하지않았기때문이다. 읽기증가없음도특정cache경계원인의증명이아니며효과미확인으로기록한다.

O1의현재최소안에서tag/type/label일치만으로는같은노드를보장못한다. 이전결론대로실제DOM노드·폼동일성,선택지,가시성,원자별중간관측과실패시미실행접두부를보존해야한다. 대화응답뒤에모델이필요해도fill+Send를묶는1호출절감후보는여전히남는다. 단95/401을수학적상한이나검증절감률로쓰지않는다.

O7은기존CLI정가추정액을없애거나덮어쓰지않는다. 공식가격으로재계산하면모델·가격표날짜·항목을명시해별도지표로보고하고청구액/구독한도효과는미측정으로남긴다.
