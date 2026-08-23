# Replica 워크플로우 현재 상태

작성일: 2026-08-22
현재 종료 지점: 제한 Component는 공개 산출물, 실제 2차 bundle은 구현 준비 완료

## 전체 흐름

```text
기업 공개 자료 조사
→ 2차 결과와 구현 계약 동결
→ Operator가 Replica 구현
→ 비공개 동결 테스트 평가
→ Completion Standard 판정
→ 공개 산출물 파일 생성
```

브라우저 UI 생성과 로컬 웹 실행기는 현재 워크플로우에 포함하지 않는다.

## 구현과 평가

준비된 `replica-second-pass-result/v1`을 받으면 공개 작업영역과 비공개 평가
Vault를 분리한다. Operator는 공개 계약만 읽고 `replicate(runtime_input)` 구현을
작성한다. 동결 테스트와 기대 출력은 구현 단계에 공개하지 않는다.

평가 단계에서는 다음을 확인한다.

- 정상, 경계, 정보 부족, 새로운 입력 사례
- 같은 입력을 반복했을 때 결과가 같은지
- 이름만 다른 중복 시험 입력이 없는지
- 실제 출력과 결정적·의미적 판정
- 구현, 입력, 결과, 보고서 digest 결속
- Completion Standard의 근거·의존성·산출물 조건

## 공개 산출물

성공한 run은 파일 묶음으로 끝난다. 대표 파일은 다음과 같다.

- `implementation/replica.py`: 실행 가능한 Replica 구현
- `implementation/manifest.json`: 실행 진입점과 명령
- `replica.json`: 실행 계획과 구현 연결 정보
- `replica-spec.json`: 입력·출력 계약
- `generated-component.json`: 고정된 생성 Component
- `replica-result.json`: 상태, 평가 요약, 지원 범위와 한계
- `completion-assessment.json`: Completion Standard 판정
- `report.json`: 기계가 읽는 보고서
- `report.md`: 사람이 읽는 보고서

비공개 평가 Vault에는 `tests.json`, 사례별 출력, 채점 결과와 평가 근거가 남는다.
이 파일들은 공개 run에 복사하지 않는다.

## 현재 지원 범위

두 경로를 지원한다.

- 기존 standalone Second-pass는 제한 expression/Python으로 구현하고 동결 평가와
  공개를 끝낸다.
- 완료된 company research는 ready/build claim의 전체 workflow, findings,
  OSS/API/license 정보와 scenario를 Sol에 보존해서 전달한다. Terra는 테스트 정답이
  제거된 Builder context와 Sol 지시를 받아 다중 파일 `implementation/` bundle,
  dependency record, 환경변수 이름과 실행 명령을 만든다.

Implementation bundle은 파일 경계와 해시까지 검증한 `IMPLEMENTATION_READY`다.
아직 dependency 설치, 격리 실행, 봉인 평가와 공개 결과 처리가 연결되지 않았으므로
`reproduced`나 `RESULT_SUCCESS`로 기록하지 않는다.

## 현재 결론

제한 Component 경로는 비공개 동결 테스트, Completion Standard 판정과 공개 파일
묶음까지 구현되어 있다. 실제 research 기반 bundle 경로는 Sol/Terra 구현 handoff와
구조 검증까지 구현되어 있으며 평가·공개 연결은 다음 단계다. UI 생성은 두 흐름에
포함하지 않는다.
