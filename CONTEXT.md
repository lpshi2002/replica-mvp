# Replica Build

공개 근거로 확인된 기업 기능을 제한된 입력과 출력의 독립 실행 가능한 기능으로 재현하고, 그 재현 범위와 한계를 명확히 표현하기 위한 도메인이다.

## Language

**Replica**:
고정된 입력 계약을 받아 실제 출력을 생성하고, 동결된 테스트를 통과하며, 사용한 공개 근거와 지원하지 않는 범위가 함께 기록된 독립 구현이다.
_Avoid_: 제품 복제본, 원제품 동등품, 디지털 트윈

**Second-pass Result**:
복제할 주장, 공개 근거, 입출력 계약, 경계, 평가 기준과 고정 테스트가 결정된 상위 조사 단계의 권위 있는 JSON 산출물이다. Replica 빌드 단계는 이 결정을 다시 선택하거나 재채점하지 않는다.
_Avoid_: 초안, 빌드 계획, Replica Handoff

**Replica Intake**:
Second-pass Result 원본을 내용 해시로 식별하여 변경 없이 보존하고 계약 검증 대기 상태로 등록한 기록이다.
_Avoid_: Replica, 검증 완료 결과

**Buildability Assessment**:
Second-pass Result의 전체 필수 계약을 허용된 실행 환경에서 구현하고 평가할 수 있는지 판정한 결과다. 일부만 구현 가능한 경우에는 blocker를 설명하지만 Replica를 만들지 않는다.
_Avoid_: Replica 평가, 부분 Replica

**Buildable**:
전체 필수 계약 각각에 허용된 구현 전략과 실행 가능한 평가 방법을 배정할 수 있는 상태다. 아직 Replica 구현이나 테스트 통과가 완료됐다는 뜻은 아니다.
_Avoid_: 구현 완료, 테스트 통과

**Criterion Coverage**:
하나의 acceptance criterion이 하나 이상의 구현 단계와 하나 이상의 실행 가능한 평가 방법에 모두 연결된 상태다. Second-pass Result가 명시적으로 비필수로 표시하지 않은 criterion은 모두 coverage가 필요하다.
_Avoid_: 부분 충족, 구현 추정

**Hard Gate**:
필수 입력, 출력 검증, 고정 테스트 실행 또는 허용된 의존성처럼 Replica 구현을 시작하기 전에 반드시 충족해야 하는 조건이다. 하나라도 실패하면 criterion coverage와 관계없이 Replica를 만들 수 없다.
_Avoid_: 낮은 점수, 선택 기준

**Deterministic-first Hybrid**:
파싱·계산·검증은 결정적 처리로 수행하고, 의미 해석이 필요한 제한된 단계에만 근거 기반 구조화 LLM과 로컬 retrieval을 사용하는 실행 전략이다.
_Avoid_: LLM-only, 무제한 코드 생성

**Evidence-bound Model Step**:
언어 추론에는 모델을 사용하지만 출력의 모든 사실값을 실행 입력이나 승인된 근거로 추적할 수 있는 처리 단계다. 근거 없는 사실값은 생성하지 않고 정보 부족으로 표시한다.
_Avoid_: 일반 지식 답변, 출처 없는 추정

**Replica Builder**:
기업명이 아니라 Second-pass Result의 계약을 기준으로 실행 계획과 기업별 Replica를 만들어내는 공통 빌드 주체다.
_Avoid_: 기업별 Runner, Replica Runtime

**Generated Component**:
기존 구성요소로 표현할 수 없는 계약 단계를 위해 Replica Builder가 생성하고, 허용 정책과 고정 테스트를 통과한 뒤에만 사용할 수 있는 제한된 구현 단위다.
_Avoid_: 임의 코드, 검증 전 생성물

**Component Generator**:
Second-pass Result에서 테스트 기대값을 제외한 계약·기준·구현 설명을 받아 제한된 Generated Component 명세를 반환하는 빌드 시점 adapter다. Generator 프로그램 자체는 신뢰된 빌드 의존성이며 생성 결과는 별도로 검증한다.
_Avoid_: Replica Runtime, 독립 Judge, 임의 코드 실행기

**Generated Component Record**:
Generator identity, 테스트를 제외한 generation request, request와 component의 내용 해시, 검증된 표현식 명세를 함께 고정한 run artifact다.
_Avoid_: 원본 Second-pass Result, 실행 결과

**Replica Spec**:
Second-pass Result에서 파생된 불변의 실행 대상 계약으로, 복제할 주장과 입출력, acceptance criteria, evidence policy를 정의한다.
_Avoid_: 실행 순서, 구현 계획

**Execution Plan**:
Replica Spec을 충족하기 위한 단계, 실행 전략, 단계 간 의존성, criterion coverage와 평가 연결을 정의한 버전 있는 계획이다.
_Avoid_: 조사 결과, Replica Spec

**Final Report**:
하나의 Replica run에 대한 빌드 상태, 평가 결과, 근거 수준, 지원 범위, 비지원 범위와 한계를 결합해 동결한 최종 결과다.
_Avoid_: 원제품 동등성 선언, 조사 결과 복사본

**Replica Build Result**:
하나의 Second-pass Result 처리 호출이 만든 최종 상태, run 경로, Replica 경로, 평가 요약과 선택적 Final Report를 호출자에게 돌려주는 결과다.
_Avoid_: Replica Spec, Final Report
