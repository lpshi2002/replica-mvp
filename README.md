# Replica MVP

공개 근거에서 하나의 관찰 가능한 AI 기능을 정의하고, 실행 가능한 Replica를 만든 뒤 독립 테스트와 별도 Judge로 평가하는 최소 CLI입니다. 원제품 출력이 없으면 동일성을 주장하지 않고 공개 기능의 구현 가능성만 보고합니다.

## 5단계

1. `evidence.json`: 기업, 기능 주장, 공개 근거와 근거 수준
2. `spec.json`: 입력·출력 계약과 통과 기준
3. `replica.json`: 공용 Runner가 실행할 Replica 프롬프트
4. `tests.json` + `results.jsonl`: 독립 사례와 판정 근거
5. `report.md`: 통과 수, 근거 수준, 확인하지 못한 범위

## 실행

```bash
PYTHONPATH=src python -m replica_mvp init work/acme \
  --name acme-risk \
  --company "Acme AI" \
  --url "https://example.com" \
  --capability "공개 재무정보에서 위험 신호를 설명한다" \
  --evidence-level public
```

생성된 `evidence.json`, `spec.json`, `tests.json`의 `CHANGE_ME` 값을 공개 근거와 독립 테스트로 교체한 뒤 빌드합니다.

```bash
PYTHONPATH=src python -m replica_mvp build work/acme
```

Replica 모델과 Judge 모델을 각각 stdin으로 프롬프트를 받고 stdout으로 답하는 명령으로 연결합니다. Judge는 `{"pass": true, "reason": "..."}` JSON만 반환해야 합니다.

```bash
PYTHONPATH=src python -m replica_mvp evaluate work/acme \
  --replica-command "YOUR_REPLICA_COMMAND" \
  --judge-command "YOUR_JUDGE_COMMAND"
```

결과는 `results.jsonl`과 `report.md`에 저장됩니다. 모델 API 키는 프로젝트 파일에 넣지 말고 연결 명령이 읽는 환경 변수로 전달합니다.

## 하네스

이 저장소는 `/Users/cho/team-ai`의 하네스에 연결되어 있지만 제품 방향은 프로젝트 로컬이며 기존 아이디어 팩을 가져오지 않습니다.

```bash
team-ai context --mode implementation "MVP 구현"
team-ai guard
```
