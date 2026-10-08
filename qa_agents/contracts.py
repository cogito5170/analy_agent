"""Semantic JSON contracts exchanged between agents.

Every agent consumes and produces one of these documents. Each document carries
a versioned ``schema`` id (``qa_<name>/<major>``) so that a consumer can refuse
input it does not understand, and IDs (REQ-*, TC-*, BUG-*) link documents
together so the orchestrator can check referential integrity between stages.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_id: str = Field(alias="schema")

    def to_json(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


Priority = Literal["P0", "P1", "P2", "P3"]


# --------------------------------------------------------------------------- #
# qa_requirement/1 — Requirement Analyst
# --------------------------------------------------------------------------- #
class InputField(Strict):
    name: str
    type: Literal["string", "email", "integer", "number"] = "string"
    location: Literal["body", "query"] = "body"
    required: bool = False
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None


class Endpoint(Strict):
    method: str
    path: str


class ErrorCase(Strict):
    when: str
    status: int
    input: dict[str, Any] = Field(default_factory=dict)
    description: str = ""


class BusinessRule(Strict):
    kind: Literal["threshold_lock", "idempotent"]
    description: str
    threshold: Optional[int] = None
    status: Optional[int] = None
    input: dict[str, Any] = Field(default_factory=dict)
    header: Optional[str] = None
    key: Optional[str] = None


class Requirement(Strict):
    id: str
    feature: str
    feature_name: str
    type: Literal["functional", "business_rule", "non_functional"]
    actor: str
    behavior: str
    expected_result: Optional[str]
    priority: Literal["high", "medium", "low"]
    endpoint: Optional[Endpoint] = None
    requires_auth: bool = False
    inputs: list[InputField] = Field(default_factory=list)
    valid_example: dict[str, Any] = Field(default_factory=dict)
    success_status: Optional[int] = None
    success_body: dict[str, Any] = Field(default_factory=dict)
    success_keys: list[str] = Field(default_factory=list)
    errors: list[ErrorCase] = Field(default_factory=list)
    rule: Optional[BusinessRule] = None
    max_response_ms: Optional[int] = None
    parent: Optional[str] = None
    business: dict[str, Any] = Field(default_factory=dict)
    testable: bool
    source_ref: str


class Ambiguity(Strict):
    req_id: str
    field: str
    issue: str
    quote: str = ""
    blocking: bool = False


class MissingRequirement(Strict):
    req_id: str
    category: str
    description: str


class RequirementAnalysis(Contract):
    schema_id: Literal["qa_requirement/1"] = Field("qa_requirement/1", alias="schema")
    product: str
    base_url: str
    auth: Optional[dict[str, Any]] = None
    reset: Optional[Endpoint] = None
    health: Optional[Endpoint] = None
    requirements: list[Requirement]
    ambiguities: list[Ambiguity]
    missing_requirements: list[MissingRequirement]
    testable: bool


# --------------------------------------------------------------------------- #
# qa_risk/1 — Risk Analyst
# --------------------------------------------------------------------------- #
class RiskFactor(Strict):
    value: float
    drivers: list[str]


class Risk(Strict):
    req_id: str
    target: str
    impact: RiskFactor
    likelihood: RiskFactor
    detectability: RiskFactor
    risk_score: float
    priority: Priority
    test_depth: Literal["exhaustive", "thorough", "standard", "smoke"]
    reason: str


class RiskAnalysis(Contract):
    schema_id: Literal["qa_risk/1"] = Field("qa_risk/1", alias="schema")
    formula: str
    priority_bands: dict[str, float]
    risks: list[Risk]


# --------------------------------------------------------------------------- #
# qa_test_plan/1 — Test Designer
# --------------------------------------------------------------------------- #
Technique = Literal[
    "happy_path",
    "equivalence_partitioning",
    "boundary_value",
    "decision_table",
    "state_transition",
    "negative",
    "security_negative",
    "performance",
    "exploratory",
]


class Expectation(Strict):
    status: Optional[int] = None
    status_in: Optional[list[int]] = None
    status_not_in: Optional[list[int]] = None
    body_contains: dict[str, Any] = Field(default_factory=dict)
    body_has_keys: list[str] = Field(default_factory=list)
    max_elapsed_ms: Optional[int] = None
    same_as_previous: Optional[str] = None
    allow_5xx: bool = False


class Step(Strict):
    method: str
    path: str
    body: Optional[dict[str, Any]] = None
    query: Optional[dict[str, Any]] = None
    headers: dict[str, str] = Field(default_factory=dict)
    auth: bool = False
    repeat: int = 1
    expect: Expectation


class TestCase(Strict):
    id: str
    req_id: str
    title: str
    technique: Technique
    also_covers: list[Technique] = Field(default_factory=list)
    priority: Priority
    focus: Optional[str] = None
    automated: bool
    steps: list[Step] = Field(default_factory=list)
    charter: Optional[str] = None
    oracle: str
    assumption: Optional[str] = None


class Skipped(Strict):
    req_id: str
    reason: str


class TestPlan(Contract):
    schema_id: Literal["qa_test_plan/1"] = Field("qa_test_plan/1", alias="schema")
    strategy: dict[str, list[Technique]]
    test_cases: list[TestCase]
    skipped_requirements: list[Skipped]


# --------------------------------------------------------------------------- #
# qa_observation/1 — Test Executor
# --------------------------------------------------------------------------- #
class AssertionResult(Strict):
    type: str
    expected: Any
    actual: Any
    passed: bool


class StepResult(Strict):
    step: int
    iteration: int
    request: dict[str, Any]
    response: Optional[dict[str, Any]]
    error: Optional[str] = None
    elapsed_ms: float
    assertions: list[AssertionResult]


class Observation(Strict):
    test_id: str
    req_id: str
    status: Literal["passed", "failed", "error", "not_run"]
    expected: str
    actual: str
    step_results: list[StepResult] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    duration_ms: float = 0.0
    attempt: int = 1
    note: Optional[str] = None


class ObservationReport(Contract):
    schema_id: Literal["qa_observation/1"] = Field("qa_observation/1", alias="schema")
    environment: dict[str, Any]
    summary: dict[str, int]
    observations: list[Observation]


# --------------------------------------------------------------------------- #
# qa_defect/1 — Defect Analyst
# --------------------------------------------------------------------------- #
Classification = Literal[
    "product_bug",
    "test_bug",
    "environment",
    "requirement_ambiguity",
    "spec_mismatch",
]


class Triage(Strict):
    test_id: str
    classification: Classification
    reason: str
    reproduced_on_rerun: Optional[bool]
    transient_noise: Optional[str] = None
    defect_id: Optional[str] = None


class Defect(Strict):
    id: str
    title: str
    req_id: str
    severity: Literal["critical", "high", "medium", "low"]
    priority: Priority
    reproduction: list[str]
    expected: str
    actual: str
    evidence: list[str]
    related_tests: list[str]
    reproducible: bool
    confidence: float


class DefectReport(Contract):
    schema_id: Literal["qa_defect/1"] = Field("qa_defect/1", alias="schema")
    triage: list[Triage]
    defects: list[Defect]
    clarifications_needed: list[dict[str, str]]


# --------------------------------------------------------------------------- #
# qa_review/1 — QA Reviewer
# --------------------------------------------------------------------------- #
class Finding(Strict):
    id: str
    check: str
    severity: Literal["blocker", "major", "minor", "info"]
    target: str
    message: str


class Review(Contract):
    schema_id: Literal["qa_review/1"] = Field("qa_review/1", alias="schema")
    verdict: Literal["pass", "conditional_pass", "fail"]
    metrics: dict[str, Any]
    findings: list[Finding]


# --------------------------------------------------------------------------- #
# qa_evidence/1 — Evidence Analyst
# --------------------------------------------------------------------------- #
class Claim(Strict):
    claim: str
    origin: Literal["pipeline", "user"]
    evidence: list[str]
    strength: Literal["strong", "moderate", "weak", "unsupported"]
    note: str = ""


class EvidenceAnalysis(Contract):
    schema_id: Literal["qa_evidence/1"] = Field("qa_evidence/1", alias="schema")
    claims: list[Claim]
    measured_metrics: dict[str, Any]


# --------------------------------------------------------------------------- #
# qa_portfolio/1 — Portfolio Architect
# --------------------------------------------------------------------------- #
class PortfolioSection(Strict):
    key: str
    title: str
    body: str
    sources: list[str]


class Portfolio(Contract):
    schema_id: Literal["qa_portfolio/1"] = Field("qa_portfolio/1", alias="schema")
    title: str
    sections: list[PortfolioSection]
    excluded_claims: list[str]
    markdown: str


REGISTRY: dict[str, type[Contract]] = {
    "qa_requirement/1": RequirementAnalysis,
    "qa_risk/1": RiskAnalysis,
    "qa_test_plan/1": TestPlan,
    "qa_observation/1": ObservationReport,
    "qa_defect/1": DefectReport,
    "qa_review/1": Review,
    "qa_evidence/1": EvidenceAnalysis,
    "qa_portfolio/1": Portfolio,
}


class ContractError(ValueError):
    pass


def load(doc: dict[str, Any]) -> Contract:
    """Parse a JSON document into its contract model, rejecting unknown schemas."""
    schema_id = doc.get("schema")
    model = REGISTRY.get(schema_id)
    if model is None:
        raise ContractError(f"unknown schema {schema_id!r}")
    return model.model_validate(doc)


def check_references(board: dict[str, Contract]) -> list[str]:
    """Return broken cross-document ID references found on the blackboard."""
    problems: list[str] = []
    req = board.get("qa_requirement/1")
    if req is None:
        return problems
    req_ids = {r.id for r in req.requirements}

    def need(ids, known, where):
        for i in ids:
            if i not in known:
                problems.append(f"{where}: unknown reference {i}")

    if (risk := board.get("qa_risk/1")) is not None:
        need([r.req_id for r in risk.risks], req_ids, "qa_risk/1")
    tc_ids: set[str] = set()
    if (plan := board.get("qa_test_plan/1")) is not None:
        tc_ids = {t.id for t in plan.test_cases}
        need([t.req_id for t in plan.test_cases], req_ids, "qa_test_plan/1")
        need([s.req_id for s in plan.skipped_requirements], req_ids, "qa_test_plan/1")
    if (obs := board.get("qa_observation/1")) is not None:
        need([o.test_id for o in obs.observations], tc_ids, "qa_observation/1")
    if (dfx := board.get("qa_defect/1")) is not None:
        need([t.test_id for t in dfx.triage], tc_ids, "qa_defect/1")
        need([d.req_id for d in dfx.defects], req_ids, "qa_defect/1")
        for d in dfx.defects:
            need(d.related_tests, tc_ids, f"qa_defect/1 {d.id}")
    return problems
