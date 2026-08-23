# Replica Build Decision Map

확정된 `replica-second-pass-result/v1`을 실제 실행 가능한 Replica로 바꾸는
현재 권위 있는 흐름을 기록한다.

## 확정 흐름

1. Second-pass JSON을 evaluator vault로 수신하고 계약과 구현 가능성을 검증한다.
2. 공개 workspace에 테스트가 제거된 Operator 요청을 만든다.
3. Codex가 `.agents/skills/build-replica-operator/SKILL.md`를 따라 새 Operator를
   작성한다.
4. 생성 명세, 계약 일치, 제한 언어와 실행 계획의 안전성을 검사한다.
5. evaluator vault의 private run에서 Operator를 격리 실행한다.
6. frozen fixed tests로 독립 결정 평가한다.
7. 실패하면 상태와 pass count만 공개하고 Codex가 최대 2회 수정한다.
8. 성공하면 실행에 필요한 파일과 평가 요약만 공개 workspace에 게시한다.

## 경로 경계

`WORKSPACE`와 `EVALUATION_VAULT`는 서로 포함되지 않는 별도 루트다.
원본 Second-pass JSON도 `WORKSPACE` 밖에 있어야 하며 내부 source는 준비 단계에서
거부한다. Operator 생성은 최초 구현 1회와 수정 최대 2회, 총 3회까지 시도한다.

공개 workspace:

- `operator-tasks/<replica_id>/<digest>/task.json`
- `operator-request.json`
- `operator.json`
- `operator-attempts.json`
- `runs/<replica_id>/<digest>/replica.json`
- generated component, execution plan, buildability, evaluation summary
- 선택적 공개 보고서

evaluator vault:

- 원본 Second-pass intake
- `second-pass.json`
- `tests.json`
- `test-suite-lock.json`
- `replica_outputs.jsonl`
- `results.jsonl`
- private evaluator run

CLI나 공개 결과 JSON은 evaluator vault 경로, 테스트 내용, 기대값 또는 사례별
채점 결과를 반환하지 않는다. 동일한 OS 사용자로 두 프로세스를 실행하면 이
경계는 암호학적 권한 격리가 아니라 구조적·운영적 격리다. 더 강한 비공개성이
필요하면 evaluator를 별도 계정, 컨테이너 또는 원격 서비스로 이동해야 한다.

## 구현 선택

등록 Operator catalog는 사용하지 않는다. Second-pass에 `implementation`이 있어도
비구속 evidence hint로만 사용하고 Codex가 새 generated component를 작성한다.
저장소의 OpenAI API generator와 외부 generator command 실행 경로도 사용하지
않는다.

지원하는 실행 형식은 제한 expression과 검증된 제한 Python이다. 두 형식 모두
network, 자격증명, 파일 접근, import, subprocess와 private-company 추정을
허용하지 않는다.

Sol/Terra Agent 경로는 완료된 company research도 직접 받는다. ready/build claim의
전체 Second-pass를 Sol에 보존하고 Terra에는 테스트 기대값과 reference facts를
제거한 `builder-context.json`을 준다. 전체 workflow가 단일 Component로 표현되지
않으면 Sol은 `implementation/manifest.json`을 요구하고 Terra는 다중 파일,
dependency source/version/license, 환경변수 이름과 실행 명령을 선언한다.

이 bundle은 경로, symlink, 선언 파일 집합과 SHA-256을 검증해
`IMPLEMENTATION_READY`로 묶는다. 아직 evaluator가 bundle dependency를 준비하고
실행하는 단계는 없으므로 이 상태는 공개 결과나 재현 성공이 아니다.

## 공개 계약

```text
replica-mvp prepare-operator SOURCE \
  --workspace WORKSPACE \
  --evaluation-vault EVALUATION_VAULT

replica-mvp finalize-operator TASK_DIR \
  --workspace WORKSPACE \
  --evaluation-vault EVALUATION_VAULT \
  [--report]

replica-mvp run-replica PUBLIC_RUN_DIR
```

성공 시 `finalize-operator`는 공개 run과 Replica 경로만 반환한다. 실패 시 Codex가
볼 수 있는 정보는 실패 유형, 시도 번호, 재시도 가능 여부와 pass count뿐이다.

## 범위

제한 Component 자동 평가 대상은 Second-pass 계약으로 충분히 정의되고 고정
테스트로 검증할 수 있는 공개 범위의 결정적 기능이다. OSS, 파일, API, 모델과
다단계 workflow는 implementation bundle로 작성할 수 있지만 아직 자동 평가·공개
범위는 아니다. 비공개 데이터와 외부 자격증명은 계약과 명시적 권한 없이는 사용할
수 없다.
