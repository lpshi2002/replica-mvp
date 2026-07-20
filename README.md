# Replica MVP

현재 Codex 대화에 기업명이나 공개 URL만 입력하면 Codex가 공개 조사, 기능 선정, 사양, 테스트, Replica 실행, Judge 판정, 보고서 생성을 맡는 최소 하네스입니다. 원제품 출력이 없으면 동일성을 주장하지 않고 공개 기능의 구현 가능성만 보고합니다.

## 5단계

1. `evidence.json`: Codex가 조사한 기업, 기능 주장, 공개 근거와 근거 수준
2. `spec.json`: Codex가 정의한 입력·출력 계약과 통과 기준
3. `replica.json`: 공용 형식으로 빌드한 Replica 프롬프트
4. `tests.json` + `results.jsonl`: 독립 사례와 판정 근거
5. `report.md`: 통과 수, 근거 수준, 확인하지 못한 범위

## 사용

현재 Codex 대화에 다음 정도만 입력합니다.

```text
Acme AI로 Replica 돌려줘. 공식 사이트는 https://example.com 이야.
```

URL을 모르면 기업명만 줘도 됩니다. Codex는 다음을 수행합니다.

1. 최신 공개 자료 검색 및 근거 수준 판정
2. 가장 검증하기 좋은 기능 하나 선정
3. `work/<company>/`에 근거·사양·독립 테스트 작성
4. Replica 결과 생성과 별도 Judge 패스
5. `results.jsonl`과 `report.md` 생성

사용자는 JSON을 편집하거나 모델 API·Codex CLI 명령을 연결하지 않습니다. 이 저장소가 Codex를 호출하는 구조도 아닙니다.

## 내부 CLI

`replica-mvp init`, `build`, `report`는 Codex가 산출물을 만들고 검증할 때 사용하는 작은 파일 도구입니다. `evaluate`의 외부 명령 Runner는 CI나 독립 재현이 필요할 때만 선택적으로 사용합니다.

## 하네스

이 저장소는 `/Users/cho/team-ai`의 하네스에 연결되어 있지만 제품 방향은 프로젝트 로컬이며 기존 아이디어 팩을 가져오지 않습니다.

```bash
team-ai context --mode implementation "MVP 구현"
team-ai guard
```
