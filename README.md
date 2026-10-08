# analy_agent — QA 조직을 Agent로 분해한 테스트 파이프라인

"QA 포트폴리오 글을 써주는 AI"가 아니다. **QA 엔지니어의 업무 프로세스를 역할별 Agent로 나누고,
Agent끼리 semantic JSON 계약으로만 협업하게 만든 시스템**이다. 실제 웹 서비스(데모 앱)를 대상으로
요구사항 분석부터 리스크 산정, 테스트 설계, 실행, 결함 분류, 자체 검토, 증거 검증, 포트폴리오 구성까지
전 과정을 수행한다.

```text
 feature spec (JSON)
        │
        ▼
 ┌──────────────────────┐  qa_requirement/1   요구사항을 테스트 가능한 형태로, 모호성·누락 식별
 │ 1 Requirement Analyst│ ─────────────────┐
 └──────────────────────┘                  ▼
 ┌──────────────────────┐  qa_risk/1        무엇을 먼저, 얼마나 깊게 테스트할지
 │ 2 Risk Analyst       │ ─────────────────┐
 └──────────────────────┘                  ▼
 ┌──────────────────────┐  qa_test_plan/1   EP·BVA·결정 테이블·상태 전이·부정·보안·성능·탐색
 │ 3 Test Designer      │ ─────────────────┐
 └──────────────────────┘                  ▼
 ┌──────────────────────┐  qa_observation/1 실제 HTTP 실행, 요청/응답/시간/assertion 증거
 │ 4 Test Executor      │ ─────────────────┐
 └──────────────────────┘                  ▼
 ┌──────────────────────┐  qa_defect/1      재실행 후 분류: 제품/테스트/환경/모호성/명세 불일치
 │ 5 Defect Analyst     │ ─────────────────┐            ── Phase 1 (핵심 5개) ──
 └──────────────────────┘                  ▼
 ┌──────────────────────┐  qa_review/1      QA 산출물 자체를 QA: 커버리지·오탐·미탐·가려진 검증
 │ 6 QA Reviewer        │ ─────────────────┐
 └──────────────────────┘                  ▼
 ┌──────────────────────┐  qa_evidence/1    "실제로 했다는 증거가 있는가?" 주장별 근거 강도
 │ 7 Evidence Analyst   │ ─────────────────┐            ── Phase 2 ──
 └──────────────────────┘                  ▼
 ┌──────────────────────┐  qa_portfolio/1   문제→리스크→전략→설계→자동화→결함→개선→결과
 │ 8 Portfolio Architect│ ──▶ portfolio.md              ── Phase 3 ──
 └──────────────────────┘
```

## 빠른 시작

```bash
pip install -r requirements.txt          # pydantic 2 하나뿐 (나머지는 표준 라이브러리)

# 데모 앱을 띄우고 8개 Agent 전체 실행
python -m qa_agents run --spec demo/spec/mini_shop.json --demo-server \
                        --claims demo/claims.json --out runs/demo

# Phase 1(핵심 5개)만
python -m qa_agents run --spec demo/spec/mini_shop.json --demo-server --phase 1

# 계약 JSON Schema 내보내기
python -m qa_agents schemas --out schemas

# 테스트 (단위 + 데모 앱 대상 end-to-end)
python -m unittest discover -s tests -t .
```

실제 서비스에 돌릴 때는 spec을 작성하고 `--base-url`을 지정하면 된다. 실행 결과 한 벌이
[`examples/mini_shop_run/`](examples/mini_shop_run/)에 커밋되어 있다. 생성된 포트폴리오는
[`examples/mini_shop_run/portfolio.md`](examples/mini_shop_run/portfolio.md)에서 볼 수 있다.

## 설계 원칙

1. **Agent는 서로 직접 대화하지 않는다.** 오케스트레이터가 계약 문서만 전달한다. 각 단계의 출력은
   JSON으로 직렬화한 뒤 다시 파싱하고(`extra="forbid"`), 약속한 schema id인지 확인하고,
   `REQ-*`/`TC-*`/`BUG-*` 참조가 상위 문서에 실제로 존재하는지 검사한다
   (`qa_agents/contracts.py`의 `check_references`).
2. **결정적(rule-based)이다.** 같은 입력에는 같은 판단이 나오고, 모든 판단에 근거가 기록된다
   (리스크 driver, 테스트 오라클, 분류 사유). LLM을 붙이더라도 같은 계약 뒤에 두면 된다.
   예를 들어 자연어 PRD를 `qa_requirement/1`로 바꾸는 단계가 그 후보다.
3. **측정하지 않은 수치는 쓰지 않는다.** Portfolio Architect는 계약 문서에 있는 값만 쓴다.
   Evidence Analyst는 사용자가 주장한 숫자가 이번 실행에서 실제로 측정된 값인지 대조한다.

## Agent별 역할

| Agent | 입력 | 출력 | 핵심 판단 |
|---|---|---|---|
| Requirement Analyst | feature spec | `qa_requirement/1` | 모호한 표현("빠르게", "적절한", "등"), 기대 결과·인터페이스·경계·에러 응답·인증 실패 응답·테스트 데이터 누락. 요구사항별 `testable` 판정. 비즈니스 규칙과 비기능 요구는 별도 REQ로 분리 |
| Risk Analyst | requirement | `qa_risk/1` | `risk = impact × (0.6·likelihood + 0.4·(1−detectability))`. 각 요인에 driver 기록(금전·보안·복잡도·변경 빈도·모호성…). P0~P3 → 테스트 깊이(smoke~exhaustive) |
| Test Designer | requirement, risk | `qa_test_plan/1` | 깊이에 따라 기법 선택. 같은 요청+기대값 케이스는 병합(`also_covers`). 명세에 없는 기준은 `assumption`으로 명시 |
| Test Executor | requirement, plan | `qa_observation/1` | 헬스체크, 테스트마다 상태 초기화, 인증 토큰 처리. 암묵적 오라클("어떤 입력에도 5xx 금지"). 테스트별 증거 파일 `evidence/TC-*.json` |
| Defect Analyst | + observation | `qa_defect/1` | 실패마다 1회 재실행하고 실패 시그니처를 비교. 일시적 503은 환경 노이즈로 처리. 가정 기반 오라클 실패는 요구사항 모호성, 4xx끼리 다르면 명세 불일치, 테스트 데이터가 명세 위반이면 테스트 결함. 같은 근본 증상은 결함 하나로 병합. 심각도·우선순위·신뢰도 산정 |
| QA Reviewer | 1~5 전체 | `qa_review/1` | 요구사항 커버리지, 고위험 부정 테스트 누락, 명세 근거 없는 기대값, 중복·과잉 테스트, 약한 오라클(미탐), 재현 불가·증거 누락(오탐), **서버 오류에 가려진 검증**, 테스트 결함, 판정 보류 |
| Evidence Analyst | 1~6 + 사용자 주장 | `qa_evidence/1` | 주장별 근거 강도: strong(실행 증거) / moderate(설계 산출물·코드) / weak(서술 문서만) / unsupported(근거 없음·파일 없음·측정 안 된 수치) |
| Portfolio Architect | 1~7 | `qa_portfolio/1` + `portfolio.md` | strong·moderate 주장만 본문에 쓰고, 나머지는 "제외한 주장"으로 따로 보여줌 |

## 데모 결과

`demo/target_app.py`(로그인·결제·검색·내 정보 API)에 결함을 심어두고 파이프라인을 돌렸다.
정답지는 [`demo/SEEDED_DEFECTS.md`](demo/SEEDED_DEFECTS.md)에 있다.

- 요구사항 8개, 모호성 4건, 누락 1건. 회원 탈퇴는 테스트 불가로 판정
- 테스트 케이스 34개(자동화 33, 탐색 차터 1). 실행 결과 통과 22, 실패 11
- 실패 11건 중 제품 결함 10건은 결함 4개로 병합했고, 1건은 요구사항 모호성으로 분류
  - BUG-001 critical: 결제 멱등성 위반(이중 결제)
  - BUG-002 high: 결제 금액 0 허용
  - BUG-003 high: 잘못된 비밀번호 입력 시 HTTP 500
  - BUG-004 medium: 이메일 길이 검증 누락 (의도적으로 심지 않았는데 경계값 분석이 찾음)
- 놓친 것: 비밀번호 최대 길이 off-by-one. BUG-003의 500에 가려졌고, Reviewer가 "BUG-003 수정 후 재검증"
  항목으로 정확히 지적했다
- 검색 첫 요청의 503은 환경 노이즈로 처리했다. 600ms 응답은 명세가 "빠르게"뿐이라 버그가 아니라 기획 확인 항목으로 올렸다
- 사용자 주장 "QA 시간을 43% 절감"은 측정값이 없어 unsupported로 판정해 포트폴리오에서 제외했다

## 디렉터리

```text
qa_agents/
  contracts.py            # 8개 계약(pydantic) + 레지스트리 + 참조 무결성 검사
  orchestrator.py         # 단계 실행, 계약 검증, 산출물/trace 기록, phase 제어
  __main__.py             # CLI
  agents/                 # 역할별 Agent 8개
demo/
  target_app.py           # 테스트 대상 앱 (결함 포함)
  spec/mini_shop.json     # 기능 명세
  claims.json             # 검증할 포트폴리오 주장 예시
  SEEDED_DEFECTS.md       # 정답지
schemas/                  # 계약 JSON Schema (자동 생성)
examples/mini_shop_run/   # 실행 결과 예시 (계약 8개 + 증거 로그 + portfolio.md)
tests/                    # 단위 테스트 + end-to-end 테스트
```

## spec 형식

`demo/spec/mini_shop.json` 참고. 기능마다 `endpoint`, `inputs`(타입·필수·길이·범위·위치),
`valid_example`, `success`, `errors`(조건별 입력과 기대 status), `rules`(`threshold_lock`·`idempotent`),
`non_functional`, `business`(금전·보안·복잡도·변경 빈도·관찰 가능성)를 적는다. 빠진 항목은
Requirement Analyst가 누락으로 보고한다. 이 보고 자체가 이 Agent의 산출물이다.

## 다음 단계

- 자연어 PRD → `qa_requirement/1` 변환을 LLM Agent로 추가 (출력은 동일 계약으로 검증)
- UI 테스트용 Playwright Executor (`qa_observation/1`에 스크린샷·콘솔 로그 증거 추가)
- 결함 수정 후 `blocked_by_defect` 테스트만 골라 재실행하는 회귀 모드
- 탐색적 테스트 세션 노트를 받아 `not_run` 차터를 결과로 닫는 입력 경로
