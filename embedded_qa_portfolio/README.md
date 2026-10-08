# BMS SIL/HIL 검증 포트폴리오

자동차·임베디드 SW 검증(HILS QA) 직무 요건을 증명하기 위한 12주 프로젝트다. 4직렬 셀 배터리 팩을
관리하는 BMS 펌웨어(C)를 만들고, 플랜트 모델과 폐루프로 연결한 SIL 리그에서 요구사항 기반 자동 검증을
CI로 돌린다. 기획은 [`SPEC.md`](SPEC.md)에 있다. 모든 기능은 채용 요건 ID(`[A03]` 등)에 연결되어 있다.

주 타깃은 HILS·SW 검증 직무이고, 부가 타깃은 임베디드 플랫폼·DevOps다 (SPEC 1-B절). 그래서 빌드 환경을
컨테이너로 표준화하고, CI 실행마다 빌드 시간·재현성·커버리지 지표를 남긴다.

> 이 프로젝트의 ISO 26262·ASPICE 관련 산출물은 해당 표준의 **개념을 적용한 학습용 산출물**이다.
> 준수나 인증을 뜻하지 않는다. 임계값과 시간 기준은 설계 가정값이다.

## 진행 상황

| 주 | 산출물 | 상태 |
|---|---|---|
| 1 | HARA-lite (`docs/D3_HARA_lite.md`), 안전 목표·SW 요구사항 v0.1, 요구사항 품질 검사기 | 완료 |
| 2 | DBC v1과 검사기, 빌드 컨테이너, 빌드 파이프라인·지표, 펌웨어 첫 기능(신호 타당성·INIT/STANDBY/FAULT) | 진행 중 |
| 2 | SW Verification Plan, TC 가이드라인 초안 | 예정 |
| 3~4 | 펌웨어 (측정·보호·CAN), 단위 테스트, 정적 분석 | 예정 |
| 5 | Simulink 플랜트 모델 + Python 모델 back-to-back | 예정 |
| 6~7 | SIL 리그, 결함 주입, pytest 시험군, 추적 매트릭스 | 예정 |
| 8 | UDS 진단, **하드웨어 키트 구입 관문** | 예정 |
| 9~12 | DFMEA, 8D, 야간 회귀, (선택) 실버스 이행, 정리 | 예정 |

1주차 관문 조건(SG 4개 이상, SWR 20개 이상, 모든 SWR에 parent): **충족** — SG 5개, 기능 4개, SWR 32개.

## 구조

```text
SPEC.md                    프로젝트 스펙 (요건 커버리지, 구성요소, 일정, 면접 대응표)
docs/
  D3_HARA_lite.md          위험 분석 → 안전 목표   [A11]
  review_log.md            검토 지적과 조치 기록
requirements/
  safety_goals.yaml        안전 목표(SG), 기능(FN)
  swr.yaml                 SW 요구사항(SWR)        [A03, A19]
can/
  bms.dbc                  CAN 데이터베이스 v0.1   [A04, A05, A16]
firmware/
  include/, src/           BMS 애플리케이션 계층, 하드웨어 독립 (구성요소 C2)   [A01]
  test/                    Unity 단위 테스트 (@verifies 태그로 요구사항 연결)
  cmake/arm-none-eabi.cmake  Cortex-M4F 크로스 컴파일 설정 (보드는 TODO)
ci/
  Dockerfile               빌드 환경 이미지 (호스트 + ARM 툴체인)   [P02]
  pipeline.sh, metrics.py  빌드→테스트→커버리지→ARM→재현성, 지표 수집   [A14, P01, P06]
tools/
  req_check.py             요구사항 품질 검사기     [A03, A19]
  dbc_lint.py              DBC 구조 검사 + 펌웨어 헤더와의 불일치 검출
tests/                     도구 시험
```

## 실행

```bash
# 검사 도구
pip install pyyaml
python tools/req_check.py                                           # 요구사항 품질 검사
python tools/dbc_lint.py can/bms.dbc --header firmware/include/bms.h  # DBC 검사
python -m unittest discover -s tests

# 펌웨어 파이프라인: CI와 같은 컨테이너에서 (권장)
docker build -t bms-ci ci
docker run --rm -v "$PWD/..":/work -w /work/embedded_qa_portfolio bms-ci bash ci/pipeline.sh build/ci

# 컨테이너 없이 (ARM 컴파일러가 없으면 ARM 단계는 skipped)
bash ci/pipeline.sh build/ci        # 결과: build/ci/metrics.json, build/ci/summary.md
```
