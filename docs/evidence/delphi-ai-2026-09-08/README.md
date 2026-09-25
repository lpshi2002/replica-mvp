# Delphi 2026-09-08 실행 증거

`work/`는 Git에서 제외되므로, 결과 문서가 인용하는 공개 범위의 요약 증거를 이
디렉터리에 복사해 팀원이 검증할 수 있게 했다. 원본 위치는
`work/delphi-ai/implementation-check-2026-09-08/`이다.

| 파일 | 원본 |
|---|---|
| `research.json` | 이번 실행에 쓴 2차 조사 보완본 |
| `agent-harness.json` | 하네스 registry(`agent-run/agent-harness.json`) |
| `run-context.json` | 실행 브랜치·소스·조사 해시 |
| `fresh-input-execution-check.json` | 새 입력 실행의 명령·입출력·처리 시간 |
| `claim-00N/replica-result.json`, `completion-assessment.json`, `manifest.json` | 최종 제출(attempt-002)의 공개 결과·판정·구현 manifest |
| `claim-00N/fresh-input-*` | claim별 새 입력 실행 기록 |
| `SHA256SUMS` | 원본 위치 기준 상대 경로의 SHA-256. 복사하지 않은 SQLite 산출물도 포함 |

복사하지 않은 것:

- `evaluator-vault/`의 봉인 테스트·사례별 결과·Judge 사유. 공개하면 봉인 평가가
  무력화된다.
- 공개 run 전체(약 300 MB, 구현 사본과 벤더링된 바이너리 포함). manifest의 파일 해시와
  `replica-result.json`의 `artifacts` 해시로 원본과 대조할 수 있다.

로컬 원본과 대조하려면 원본 디렉터리에서
`shasum -a 256 -c <저장소>/docs/evidence/delphi-ai-2026-09-08/SHA256SUMS`를 실행한다.
이후 실행도 같은 방식으로 `docs/evidence/<company>-<date>/`에 공개 범위의 요약 증거와
해시를 남긴다.

주의: 이 `research.json`은 9/8 보완 스크립트가 세 claim의 readiness를 `ready`로
덮어쓴 버전이며, 상단 집계는 ready 2개로 남아 있다. 현재 파서는 이 파일을 집계 불일치,
단계 대응표(`step_coverage`) 누락, 인용 없는 출처로 거부한다. 기록 보존용이며 새 실행의
입력으로 쓰지 않는다.
