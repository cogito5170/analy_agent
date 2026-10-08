"""Portfolio Architect — turns the run into one project story.

Problem → Risk → Strategy → Design → Automation → Defects → Improvement → Result

It writes only what the upstream contracts contain. Every number comes from a
contract or from the Evidence Analyst's measured metrics, and only claims rated
strong or moderate make it into the Result section; the rest are listed as
excluded so the author can see what they cannot say yet.
"""

from __future__ import annotations

from ..contracts import (
    DefectReport,
    EvidenceAnalysis,
    ObservationReport,
    Portfolio,
    PortfolioSection,
    RequirementAnalysis,
    Review,
    RiskAnalysis,
    TestPlan,
)
from .base import Agent, Board

TECHNIQUE_KO = {
    "happy_path": "정상 흐름",
    "equivalence_partitioning": "동등 분할",
    "boundary_value": "경계값 분석",
    "decision_table": "결정 테이블",
    "state_transition": "상태 전이",
    "negative": "부정 테스트",
    "security_negative": "보안 부정 테스트",
    "performance": "성능(응답시간)",
    "exploratory": "탐색적 테스트",
}
CLASS_KO = {
    "product_bug": "제품 결함",
    "test_bug": "테스트 결함",
    "environment": "환경 문제",
    "requirement_ambiguity": "요구사항 모호성",
    "spec_mismatch": "명세 불일치(확인 필요)",
}


def _table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c).replace("|", "\\|") for c in row) + " |" for row in rows]
    return "\n".join(out)


class PortfolioArchitect(Agent):
    name = "Portfolio Architect"
    consumes = ("qa_requirement/1", "qa_risk/1", "qa_test_plan/1", "qa_observation/1",
                "qa_defect/1", "qa_review/1", "qa_evidence/1")
    produces = "qa_portfolio/1"

    def __init__(self, file_names: dict[str, str]):
        self.files = file_names

    def run(self, board: Board) -> Portfolio:
        req: RequirementAnalysis = board["qa_requirement/1"]
        risk: RiskAnalysis = board["qa_risk/1"]
        plan: TestPlan = board["qa_test_plan/1"]
        obs: ObservationReport = board["qa_observation/1"]
        dfx: DefectReport = board["qa_defect/1"]
        review: Review = board["qa_review/1"]
        ev: EvidenceAnalysis = board["qa_evidence/1"]
        m = ev.measured_metrics
        f = self.files
        reqs = {r.id: r for r in req.requirements}
        sections: list[PortfolioSection] = []

        def add(key, title, body, *schemas):
            sections.append(PortfolioSection(key=key, title=title, body=body.strip(),
                                             sources=[f[s] for s in schemas]))

        untestable = [r for r in req.requirements if not r.testable]
        amb_rows = [[a.req_id, reqs[a.req_id].feature_name, a.issue] for a in req.ambiguities]
        miss_rows = [[x.req_id, reqs[x.req_id].feature_name, x.category, x.description]
                     for x in req.missing_requirements]
        add("problem", "1. 문제 정의 — 요구사항을 테스트 가능한 형태로", f"""
대상: **{req.product}**. 기능 명세를 요구사항 {m['requirements_total']}개(기능·비즈니스 규칙·비기능)로 나누고,
각 요구사항이 테스트 가능한지 판정했다. 테스트 가능: {m['requirements_testable']}개,
불가: {len(untestable)}개 ({', '.join(r.feature_name for r in untestable) or '없음'}).

**모호성 {len(req.ambiguities)}건**

{_table(['요구사항', '기능', '문제'], amb_rows) if amb_rows else '없음'}

**누락된 요구사항 {len(req.missing_requirements)}건**

{_table(['요구사항', '기능', '분류', '내용'], miss_rows) if miss_rows else '없음'}
""", "qa_requirement/1")

        risk_rows = [[r.req_id, r.target, f"{r.impact.value:.2f}", f"{r.likelihood.value:.2f}",
                      f"{r.detectability.value:.2f}", f"**{r.risk_score:.3f}**", r.priority, r.test_depth]
                     for r in risk.risks]
        add("risk", "2. 리스크 분석 — 무엇을 먼저 테스트할 것인가", f"""
모든 것을 테스트할 수 없으므로 요구사항마다 리스크 점수를 계산해 우선순위와 테스트 깊이를 정했다.

`risk = {risk.formula}`

{_table(['요구사항', '대상', '영향도', '발생가능성', '탐지가능성', '점수', '우선순위', '깊이'], risk_rows)}

가장 높은 리스크: **{risk.risks[0].target}** — {risk.risks[0].reason}
""", "qa_risk/1")

        strat_rows = [[rid, reqs[rid].feature_name, ", ".join(TECHNIQUE_KO[t] for t in ts)]
                      for rid, ts in plan.strategy.items()]
        skipped = "\n".join(f"- {s.req_id} ({reqs[s.req_id].feature_name}): {s.reason}"
                            for s in plan.skipped_requirements) or "- 없음"
        add("strategy", "3. 테스트 전략 — 리스크에 비례한 기법 선택", f"""
리스크 등급이 높을수록 더 많은 기법을 적용했다 (P3 smoke → P0 exhaustive).

{_table(['요구사항', '기능', '적용 기법'], strat_rows)}

설계에서 제외한 요구사항:
{skipped}
""", "qa_risk/1", "qa_test_plan/1")

        tech_rows = [[TECHNIQUE_KO.get(k, k), v] for k, v in
                     sorted(m["techniques"].items(), key=lambda kv: -kv[1])]
        examples = []
        shown = set()
        for tc in plan.test_cases:
            if tc.technique in shown:
                continue
            shown.add(tc.technique)
            examples.append([tc.id, TECHNIQUE_KO[tc.technique], tc.title, tc.oracle])
        add("design", "4. 테스트 설계", f"""
테스트 케이스 {m['test_cases_total']}개 (자동화 {m['test_cases_automated']}개). 같은 요청·기대값을 만드는 케이스는
하나로 합치고 다른 기법은 `also_covers`로 기록해 중복 실행을 없앴다.

{_table(['기법', '케이스 수(병합 포함)'], tech_rows)}

기법별 예시:

{_table(['ID', '기법', '제목', '오라클'], examples)}
""", "qa_test_plan/1")

        add("automation", "5. 자동화 실행", f"""
환경: `{obs.environment.get('base_url')}` · 헬스체크 `{obs.environment.get('health_check')}` ·
격리: {obs.environment.get('isolation')}.

실행 {m['tests_executed']}개 중 통과 {m['tests_passed']}개, 실패 {m['tests_failed']}개
(통과율 {m['pass_rate_pct']}%), 미실행(수동 차터) {obs.summary.get('not_run', 0)}개.
모든 테스트의 요청·응답·시간·assertion은 `evidence/<테스트 ID>.json`에 남겼다.
""", "qa_observation/1")

        tri_rows = [[CLASS_KO[k], v] for k, v in m["triage"].items()]
        bug_rows = [[d.id, d.severity, d.priority, d.title, len(d.related_tests),
                     "예" if d.reproducible else "아니오", d.confidence] for d in dfx.defects]
        details = []
        for d in dfx.defects:
            steps = "\n".join(f"   {i}. {s}" for i, s in enumerate(d.reproduction, 1))
            details.append(f"""**{d.id} {d.title}**

- 심각도/우선순위: {d.severity} / {d.priority} · 신뢰도 {d.confidence}
- 재현 절차:
{steps}
- 기대: `{d.expected}`
- 실제: `{d.actual}`
- 관련 테스트: {', '.join(d.related_tests)}
- 증거: {', '.join(f'`{e}`' for e in d.evidence)}""")
        clar = "\n".join(f"- {c['req_id']} / {c['test_id']}: {c['question']}"
                         for c in dfx.clarifications_needed) or "- 없음"
        add("defects", "6. 결함 분석 — 실패를 곧바로 버그로 부르지 않는다", f"""
실패한 테스트는 모두 한 번 재실행한 뒤 분류했다.

{_table(['분류', '건수'], tri_rows) if tri_rows else '실패 없음'}

같은 근본 증상(같은 엔드포인트, 같은 위반 유형)의 실패는 하나의 결함으로 묶었다.

{_table(['ID', '심각도', '우선순위', '제목', '관련 테스트', '재현', '신뢰도'], bug_rows) if bug_rows else '결함 없음'}

{(chr(10) * 2).join(details)}

제품 결함이 아닌 실패 중 기획 확인이 필요한 항목:
{clar}
""", "qa_defect/1")

        important = [x for x in review.findings if x.severity in ("blocker", "major")]
        rev_rows = [[x.id, x.severity, x.check, x.target, x.message] for x in important]
        add("improvement", "7. 개선 — QA 산출물 자체에 대한 검토", f"""
QA Reviewer가 요구사항 커버리지, 기대값 근거, 약한 오라클(미탐), 재현성·증거(오탐), 중복·과잉 테스트,
테스트 자체의 결함을 검토했다. 판정: **{review.verdict}** (전체 지적 {len(review.findings)}건).

{_table(['ID', '심각도', '검사', '대상', '내용'], rev_rows) if rev_rows else '주요 지적 없음'}
""", "qa_review/1")

        kept = [c for c in ev.claims if c.strength in ("strong", "moderate")]
        excluded = [c for c in ev.claims if c.strength not in ("strong", "moderate")]
        res_rows = [[c.strength, c.claim, ", ".join(e.removeprefix("run:") for e in c.evidence[:3])
                     + (f" 외 {len(c.evidence) - 3}개" if len(c.evidence) > 3 else "")] for c in kept]
        exc_rows = [[c.strength, c.claim, c.note] for c in excluded]
        add("result", "8. 결과 — 증거로 뒷받침되는 주장만", f"""
{_table(['근거 강도', '주장', '증거'], res_rows)}

**포트폴리오에서 제외한 주장** (근거 부족)

{_table(['근거 강도', '주장', '사유'], exc_rows) if exc_rows else '없음'}
""", "qa_evidence/1")

        title = f"{req.product} QA 프로젝트 — 리스크 기반 테스트 설계부터 결함 분석까지"
        md = [f"# {title}", "",
              "> 이 문서는 QA Agent 파이프라인이 생성한 계약(JSON) 산출물만으로 구성되었으며, "
              "측정되지 않은 수치는 포함하지 않는다.", ""]
        for s in sections:
            md += [f"## {s.title}", "", s.body, "", f"<sub>출처: {', '.join(s.sources)}</sub>", ""]
        return Portfolio(title=title, sections=sections,
                         excluded_claims=[c.claim for c in excluded], markdown="\n".join(md))
