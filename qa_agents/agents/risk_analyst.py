"""Risk Analyst — decides what to test first and how deeply.

Everything cannot be tested, so each requirement gets a risk score from three
factors, each with the drivers that produced it so the score can be argued with:

* impact         — how bad a defect here would be (money, security, reach)
* likelihood     — how likely a defect here is (complexity, churn, ambiguity)
* detectability  — how likely a defect would be noticed before users hit it

    risk = impact × (0.6 × likelihood + 0.4 × (1 − detectability))

The score maps to a priority band, and the band to a test depth that the Test
Designer uses to pick techniques.
"""

from __future__ import annotations

from ..contracts import Requirement, RequirementAnalysis, Risk, RiskAnalysis, RiskFactor
from .base import Agent, Board

FORMULA = "impact × (0.6 × likelihood + 0.4 × (1 − detectability))"
BANDS = {"P0": 0.55, "P1": 0.35, "P2": 0.20, "P3": 0.0}
DEPTH = {"P0": "exhaustive", "P1": "thorough", "P2": "standard", "P3": "smoke"}
LEVEL = {"low": 0.2, "medium": 0.4, "high": 0.6}


def _clamp(v: float, lo: float = 0.05, hi: float = 0.99) -> float:
    return round(max(lo, min(hi, v)), 3)


class RiskAnalyst(Agent):
    name = "Risk Analyst"
    consumes = ("qa_requirement/1",)
    produces = "qa_risk/1"

    def run(self, board: Board) -> RiskAnalysis:
        analysis: RequirementAnalysis = board["qa_requirement/1"]
        amb_count: dict[str, int] = {}
        for a in analysis.ambiguities:
            amb_count[a.req_id] = amb_count.get(a.req_id, 0) + 1
        miss_count: dict[str, int] = {}
        for m in analysis.missing_requirements:
            miss_count[m.req_id] = miss_count.get(m.req_id, 0) + 1

        risks = [self._assess(r, amb_count.get(r.id, 0), miss_count.get(r.id, 0))
                 for r in analysis.requirements]
        risks.sort(key=lambda r: -r.risk_score)
        return RiskAnalysis(formula=FORMULA, priority_bands=BANDS, risks=risks)

    def _assess(self, req: Requirement, ambiguities: int, missing: int) -> Risk:
        b = req.business

        impact, i_drivers = LEVEL[req.priority], [f"요구 우선순위 {req.priority} (+{LEVEL[req.priority]})"]
        if b.get("money"):
            impact += 0.25
            i_drivers.append("금전 처리 (+0.25)")
        if b.get("security"):
            impact += 0.15
            i_drivers.append("보안/인증 관련 (+0.15)")
        if b.get("users") == "all":
            impact += 0.05
            i_drivers.append("전체 사용자 영향 (+0.05)")
        if req.type == "business_rule":
            impact += 0.1
            i_drivers.append("비즈니스 규칙 위반 시 데이터 무결성 훼손 (+0.1)")

        likelihood = LEVEL.get(b.get("complexity", "medium"), 0.4)
        l_drivers = [f"복잡도 {b.get('complexity', 'medium')} (+{likelihood})"]
        churn = {"low": 0.0, "medium": 0.1, "high": 0.2}.get(b.get("change_frequency", "medium"), 0.1)
        if churn:
            likelihood += churn
            l_drivers.append(f"변경 빈도 {b.get('change_frequency')} (+{churn})")
        if req.inputs:
            bump = round(0.03 * len(req.inputs), 2)
            likelihood += bump
            l_drivers.append(f"입력 {len(req.inputs)}개 (+{bump})")
        if req.type == "business_rule":
            likelihood += 0.1
            l_drivers.append("상태 의존 로직 (+0.1)")
        if ambiguities or missing:
            bump = round(min(0.3, 0.1 * ambiguities + 0.05 * missing), 2)
            likelihood += bump
            l_drivers.append(f"모호성 {ambiguities}건 / 누락 {missing}건 (+{bump})")

        detectability = 0.6 if b.get("observable", True) else 0.3
        d_drivers = ["실패가 사용자 화면/응답에 바로 드러남 (0.6)" if b.get("observable", True)
                     else "실패가 조용히 일어나 발견이 늦음 (0.3)"]
        if req.type == "non_functional":
            detectability = 0.5
            d_drivers = ["성능 저하는 점진적으로 드러남 (0.5)"]
        if req.type == "business_rule":
            detectability -= 0.1
            d_drivers.append("단일 요청으로는 드러나지 않음 (−0.1)")

        impact, likelihood, detectability = _clamp(impact), _clamp(likelihood), _clamp(detectability)
        score = round(impact * (0.6 * likelihood + 0.4 * (1 - detectability)), 3)
        priority = next(p for p, floor in BANDS.items() if score >= floor)

        reason = f"영향도 근거: {', '.join(i_drivers[1:]) or i_drivers[0]}"
        if not req.testable:
            reason += " / 현재 요구사항으로는 테스트 불가 — 명세 보완이 선행되어야 함"

        return Risk(
            req_id=req.id,
            target=f"{req.feature_name} ({req.type})",
            impact=RiskFactor(value=impact, drivers=i_drivers),
            likelihood=RiskFactor(value=likelihood, drivers=l_drivers),
            detectability=RiskFactor(value=detectability, drivers=d_drivers),
            risk_score=score,
            priority=priority,
            test_depth=DEPTH[priority],
            reason=reason,
        )
