# Mini Shop QA 프로젝트 — 리스크 기반 테스트 설계부터 결함 분석까지

> 이 문서는 QA Agent 파이프라인이 생성한 계약(JSON) 산출물만으로 구성되었으며, 측정되지 않은 수치는 포함하지 않는다.

## 1. 문제 정의 — 요구사항을 테스트 가능한 형태로

대상: **Mini Shop**. 기능 명세를 요구사항 8개(기능·비즈니스 규칙·비기능)로 나누고,
각 요구사항이 테스트 가능한지 판정했다. 테스트 가능: 7개,
불가: 1개 (회원 탈퇴).

**모호성 4건**

| 요구사항 | 기능 | 문제 |
|---|---|---|
| REQ-005 | 상품 검색 | 모호한 표현 '빠르게' — 검증 가능한 기준으로 바꿔야 함 |
| REQ-006 | 상품 검색 | 정량 기준이 없어 합격/불합격을 판정할 수 없음 (목표 응답시간 필요) |
| REQ-008 | 회원 탈퇴 | 모호한 표현 '적절한' — 검증 가능한 기준으로 바꿔야 함 |
| REQ-008 | 회원 탈퇴 | 기대 결과가 정의되지 않아 테스트 오라클을 만들 수 없음 |

**누락된 요구사항 1건**

| 요구사항 | 기능 | 분류 | 내용 |
|---|---|---|---|
| REQ-008 | 회원 탈퇴 | interface | 관찰 가능한 인터페이스(API/화면)가 정의되지 않음 |

<sub>출처: 01_requirement.json</sub>

## 2. 리스크 분석 — 무엇을 먼저 테스트할 것인가

모든 것을 테스트할 수 없으므로 요구사항마다 리스크 점수를 계산해 우선순위와 테스트 깊이를 정했다.

`risk = impact × (0.6 × likelihood + 0.4 × (1 − detectability))`

| 요구사항 | 대상 | 영향도 | 발생가능성 | 탐지가능성 | 점수 | 우선순위 | 깊이 |
|---|---|---|---|---|---|---|---|
| REQ-004 | 결제 (business_rule) | 0.99 | 0.93 | 0.20 | **0.869** | P0 | exhaustive |
| REQ-003 | 결제 (functional) | 0.99 | 0.83 | 0.30 | **0.770** | P0 | exhaustive |
| REQ-002 | 로그인 (business_rule) | 0.90 | 0.66 | 0.50 | **0.536** | P1 | thorough |
| REQ-008 | 회원 탈퇴 (functional) | 0.60 | 0.65 | 0.30 | **0.402** | P1 | thorough |
| REQ-001 | 로그인 (functional) | 0.80 | 0.56 | 0.60 | **0.397** | P1 | thorough |
| REQ-006 | 상품 검색 (non_functional) | 0.45 | 0.43 | 0.50 | **0.206** | P2 | standard |
| REQ-005 | 상품 검색 (functional) | 0.45 | 0.43 | 0.60 | **0.188** | P3 | smoke |
| REQ-007 | 내 정보 조회 (functional) | 0.40 | 0.20 | 0.60 | **0.112** | P3 | smoke |

가장 높은 리스크: **결제 (business_rule)** — 영향도 근거: 금전 처리 (+0.25), 보안/인증 관련 (+0.15), 비즈니스 규칙 위반 시 데이터 무결성 훼손 (+0.1)

<sub>출처: 02_risk.json</sub>

## 3. 테스트 전략 — 리스크에 비례한 기법 선택

리스크 등급이 높을수록 더 많은 기법을 적용했다 (P3 smoke → P0 exhaustive).

| 요구사항 | 기능 | 적용 기법 |
|---|---|---|
| REQ-004 | 결제 | 상태 전이 |
| REQ-003 | 결제 | 정상 흐름, 부정 테스트, 동등 분할, 경계값 분석, 보안 부정 테스트, 탐색적 테스트 |
| REQ-002 | 로그인 | 상태 전이 |
| REQ-001 | 로그인 | 정상 흐름, 부정 테스트, 동등 분할, 경계값 분석, 결정 테이블, 보안 부정 테스트 |
| REQ-006 | 상품 검색 | 성능(응답시간) |
| REQ-005 | 상품 검색 | 정상 흐름, 부정 테스트 |
| REQ-007 | 내 정보 조회 | 정상 흐름, 부정 테스트 |

설계에서 제외한 요구사항:
- REQ-008 (회원 탈퇴): 요구사항이 테스트 가능하지 않음 (Requirement Analyst 판정)

<sub>출처: 02_risk.json, 03_test_plan.json</sub>

## 4. 테스트 설계

테스트 케이스 34개 (자동화 33개). 같은 요청·기대값을 만드는 케이스는
하나로 합치고 다른 기법은 `also_covers`로 기록해 중복 실행을 없앴다.

| 기법 | 케이스 수(병합 포함) |
|---|---|
| 경계값 분석 | 10 |
| 동등 분할 | 6 |
| 부정 테스트 | 5 |
| 정상 흐름 | 4 |
| 결정 테이블 | 4 |
| 보안 부정 테스트 | 4 |
| 상태 전이 | 2 |
| 탐색적 테스트 | 1 |
| 성능(응답시간) | 1 |

기법별 예시:

| ID | 기법 | 제목 | 오라클 |
|---|---|---|---|
| TC-PAYMENT-001 | 상태 전이 | 결제 같은 Idempotency-Key로 재시도 | 두 응답의 'payment_id'가 같아야 함 (중복 처리 없음) |
| TC-PAYMENT-002 | 정상 흐름 | 결제 유효한 입력으로 요청 | status 200 및 성공 응답 본문 |
| TC-PAYMENT-003 | 부정 테스트 | 결제 인증 없이 요청 | status 401 |
| TC-PAYMENT-004 | 동등 분할 | 결제 필수 입력 'amount' 누락 | status 400 |
| TC-PAYMENT-006 | 경계값 분석 | 결제 'amount' 최솟값-1(0) | status 400 |
| TC-PAYMENT-010 | 탐색적 테스트 | 결제 탐색적 테스트 차터 | 테스터 판단 (세션 노트로 기록) |
| TC-LOGIN-015 | 결정 테이블 | 로그인 결정 테이블 [email=X, password=X] | 모든 필수 입력이 있을 때만 성공 |
| TC-LOGIN-016 | 보안 부정 테스트 | 로그인 'email'에 주입 문자열 입력 | 인증 우회 없음, 5xx 없음 |
| TC-SEARCH-001 | 성능(응답시간) | 상품 검색 응답 시간 500ms 이내 | 3회 모두 500ms 이내 |

<sub>출처: 03_test_plan.json</sub>

## 5. 자동화 실행

환경: `http://127.0.0.1:32919` · 헬스체크 `GET /health -> 200` ·
격리: reset before each test.

실행 33개 중 통과 22개, 실패 11개
(통과율 66.7%), 미실행(수동 차터) 1개.
모든 테스트의 요청·응답·시간·assertion은 `evidence/<테스트 ID>.json`에 남겼다.

<sub>출처: 04_observation.json</sub>

## 6. 결함 분석 — 실패를 곧바로 버그로 부르지 않는다

실패한 테스트는 모두 한 번 재실행한 뒤 분류했다.

| 분류 | 건수 |
|---|---|
| 제품 결함 | 10 |
| 요구사항 모호성 | 1 |

같은 근본 증상(같은 엔드포인트, 같은 위반 유형)의 실패는 하나의 결함으로 묶었다.

| ID | 심각도 | 우선순위 | 제목 | 관련 테스트 | 재현 | 신뢰도 |
|---|---|---|---|---|---|---|
| BUG-001 | critical | P0 | 결제: 같은 Idempotency-Key로 재시도 시 같은 요청이 중복 처리됨 | 1 | 예 | 0.95 |
| BUG-002 | high | P1 | 결제: 'amount' 최솟값-1(0) 시 입력 검증 없이 HTTP 200 응답 | 1 | 예 | 0.91 |
| BUG-003 | high | P1 | 로그인: 잘못된 비밀번호 시 HTTP 500 서버 오류 발생 | 7 | 예 | 0.99 |
| BUG-004 | medium | P2 | 로그인: 'email' 최대 길이+1(255자) 시 입력 검증 없이 HTTP 401 응답 | 1 | 예 | 0.91 |

**BUG-001 결제: 같은 Idempotency-Key로 재시도 시 같은 요청이 중복 처리됨**

- 심각도/우선순위: critical / P0 · 신뢰도 0.95
- 재현 절차:
   1. 테스트 계정으로 로그인해 토큰을 발급받는다
   2. POST /api/payments 요청 (데이터 {"amount": 15000}, 헤더 ['Idempotency-Key'])
   3. POST /api/payments 요청 (데이터 {"amount": 15000}, 헤더 ['Idempotency-Key'])
- 기대: `same_as_previous.payment_id = e1f2d33c2054`
- 실제: `same_as_previous.payment_id = d54fed014620 at step 2`
- 관련 테스트: TC-PAYMENT-001
- 증거: `evidence/TC-PAYMENT-001.attempt2.json`, `evidence/TC-PAYMENT-001.json`

**BUG-002 결제: 'amount' 최솟값-1(0) 시 입력 검증 없이 HTTP 200 응답**

- 심각도/우선순위: high / P1 · 신뢰도 0.91
- 재현 절차:
   1. 테스트 계정으로 로그인해 토큰을 발급받는다
   2. POST /api/payments 요청 (데이터 {"amount": 0})
- 기대: `status = 400`
- 실제: `status = 200 at step 1`
- 관련 테스트: TC-PAYMENT-006
- 증거: `evidence/TC-PAYMENT-006.attempt2.json`, `evidence/TC-PAYMENT-006.json`

**BUG-003 로그인: 잘못된 비밀번호 시 HTTP 500 서버 오류 발생**

- 심각도/우선순위: high / P1 · 신뢰도 0.99
- 재현 절차:
   1. POST /api/login 요청 (데이터 {"email": "alice@example.com", "password": "Wrong#Pass99"})
- 기대: `no_5xx = status < 500`
- 실제: `no_5xx = 500 at step 1`
- 관련 테스트: TC-LOGIN-004, TC-LOGIN-012, TC-LOGIN-013, TC-LOGIN-014, TC-LOGIN-018, TC-LOGIN-019, TC-LOGIN-001
- 증거: `evidence/TC-LOGIN-001.attempt2.json`, `evidence/TC-LOGIN-001.json`, `evidence/TC-LOGIN-004.attempt2.json`, `evidence/TC-LOGIN-004.json`, `evidence/TC-LOGIN-012.attempt2.json`, `evidence/TC-LOGIN-012.json`, `evidence/TC-LOGIN-013.attempt2.json`, `evidence/TC-LOGIN-013.json`, `evidence/TC-LOGIN-014.attempt2.json`, `evidence/TC-LOGIN-014.json`, `evidence/TC-LOGIN-018.attempt2.json`, `evidence/TC-LOGIN-018.json`, `evidence/TC-LOGIN-019.attempt2.json`, `evidence/TC-LOGIN-019.json`

**BUG-004 로그인: 'email' 최대 길이+1(255자) 시 입력 검증 없이 HTTP 401 응답**

- 심각도/우선순위: medium / P2 · 신뢰도 0.91
- 재현 절차:
   1. POST /api/login 요청 (데이터 {"email": "aaaaaa…(255자)", "password": "Correct#Pass1"})
- 기대: `status = 400`
- 실제: `status = 401 at step 1`
- 관련 테스트: TC-LOGIN-010
- 증거: `evidence/TC-LOGIN-010.attempt2.json`, `evidence/TC-LOGIN-010.json`

제품 결함이 아닌 실패 중 기획 확인이 필요한 항목:
- REQ-006 / TC-SEARCH-001: 요구사항에 정량 기준이 없어 500ms로 가정 — 명확화 필요 (관찰값: elapsed_ms = 601.7 at step 1)

<sub>출처: 05_defect.json</sub>

## 7. 개선 — QA 산출물 자체에 대한 검토

QA Reviewer가 요구사항 커버리지, 기대값 근거, 약한 오라클(미탐), 재현성·증거(오탐), 중복·과잉 테스트,
테스트 자체의 결함을 검토했다. 판정: **conditional_pass** (전체 지적 6건).

| ID | 심각도 | 검사 | 대상 | 내용 |
|---|---|---|---|---|
| RV-001 | major | requirement_coverage | REQ-008 | 회원 탈퇴: 요구사항이 테스트 불가 상태라 검증되지 않음 — 명세 보완 후 재설계 필요 |
| RV-003 | major | blocked_by_defect | TC-LOGIN-012,TC-LOGIN-013,TC-LOGIN-014,TC-LOGIN-018,TC-LOGIN-019,TC-LOGIN-001 | BUG-003의 서버 오류에 가려 이 테스트들의 본래 검증(경계값·상태 전이 등)이 수행되지 않음 — BUG-003 수정 후 재실행 필요 |
| RV-005 | major | open_question | TC-SEARCH-001 | 판정 보류 (requirement_ambiguity): 첫 실행은 일시적 HTTP 503(환경) — 재실행 결과로 판정. 테스트 오라클이 가정에 기반함: 요구사항에 정량 기준이 없어 500ms로 가정 — 명확화 필요 |

<sub>출처: 06_review.json</sub>

## 8. 결과 — 증거로 뒷받침되는 주장만

| 근거 강도 | 주장 | 증거 |
|---|---|---|
| moderate | 기능 명세를 요구사항 8개로 구조화하고 모호성 4건, 누락 1건을 식별했다 | 01_requirement.json |
| moderate | 리스크 점수(영향도·발생가능성·탐지가능성)로 우선순위를 산정했다 (P0 2개, P1 3개) | 02_risk.json |
| moderate | 테스트 기법 9종으로 테스트 케이스 34개를 설계했다 | 03_test_plan.json |
| strong | 자동화 테스트 33개를 실행했다 (통과 22, 실패 11) | 04_observation.json, evidence/TC-LOGIN-001.json, evidence/TC-LOGIN-002.json 외 31개 |
| strong | 실패 11건을 재실행 후 제품 결함/테스트 결함/환경/요구사항 모호성으로 분류했다 | 05_defect.json |
| strong | BUG-001 (critical) 결제: 같은 Idempotency-Key로 재시도 시 같은 요청이 중복 처리됨 | evidence/TC-PAYMENT-001.attempt2.json, evidence/TC-PAYMENT-001.json |
| strong | BUG-002 (high) 결제: 'amount' 최솟값-1(0) 시 입력 검증 없이 HTTP 200 응답 | evidence/TC-PAYMENT-006.attempt2.json, evidence/TC-PAYMENT-006.json |
| strong | BUG-003 (high) 로그인: 잘못된 비밀번호 시 HTTP 500 서버 오류 발생 | evidence/TC-LOGIN-001.attempt2.json, evidence/TC-LOGIN-001.json, evidence/TC-LOGIN-004.attempt2.json 외 11개 |
| strong | BUG-004 (medium) 로그인: 'email' 최대 길이+1(255자) 시 입력 검증 없이 HTTP 401 응답 | evidence/TC-LOGIN-010.attempt2.json, evidence/TC-LOGIN-010.json |
| moderate | QA 산출물 자체를 검토해 개선점 6건을 도출했다 (판정: conditional_pass) | 06_review.json |
| strong | 로그인 기능을 자동화 테스트했다 | 04_observation.json, qa_agents/agents/test_executor.py |
| strong | 결제 재시도 시 중복 결제되는 결함을 발견했다 | 05_defect.json |
| moderate | 리스크 기반 테스트 전략을 설계했다 | 02_risk.json, 03_test_plan.json |

**포트폴리오에서 제외한 주장** (근거 부족)

| 근거 강도 | 주장 | 사유 |
|---|---|---|
| unsupported | 테스트 자동화로 QA 시간을 43% 절감했다 | 측정되지 않은 수치 ['43'] — 실제 측정값으로 바꾸거나 삭제 |
| unsupported | 테스트 품질을 향상시켰다 | 근거 산출물이 제시되지 않음 |
| weak | QA 프로세스를 문서화했다 | 서술 문서만 존재 |

<sub>출처: 07_evidence.json</sub>
