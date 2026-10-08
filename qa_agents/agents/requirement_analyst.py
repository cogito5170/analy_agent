"""Requirement Analyst — turns a feature spec into testable requirements.

The point of this agent is not to restate the spec but to decide, per
requirement, whether it can be tested as written: is there an observable
interface, an expected result, a boundary for every input, an error path?
Anything that would force a tester to guess is reported as an ambiguity or a
missing requirement.
"""

from __future__ import annotations

import re
from typing import Any

from ..contracts import (
    Ambiguity,
    BusinessRule,
    Endpoint,
    ErrorCase,
    InputField,
    MissingRequirement,
    Requirement,
    RequirementAnalysis,
)
from .base import Agent, Board

# Words that sound like a requirement but give a tester nothing to assert.
VAGUE_TERMS = [
    "빠르게", "신속", "적절한", "적절히", "충분히", "쉽게", "간편", "원활",
    "대부분", "가능한 한", "최적", "효율적", "사용자 친화", "직관적", "자연스럽",
    "fast", "quickly", "appropriate", "easy", "user-friendly", "efficient", "intuitive",
]
ETC_RE = re.compile(r"(?:^|\s)(등|etc\.?)(?=[을의이은과\s.,]|$)")
NUMBER_MS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(ms|밀리초|초|s\b)")


def _vague_terms(text: str) -> list[str]:
    found = [t for t in VAGUE_TERMS if t.lower() in text.lower()]
    found += [m.group(1) for m in ETC_RE.finditer(text)]
    return found


def _threshold_ms(text: str) -> int | None:
    m = NUMBER_MS_RE.search(text)
    if not m:
        return None
    value, unit = float(m.group(1)), m.group(2)
    return int(value if unit in ("ms", "밀리초") else value * 1000)


class RequirementAnalyst(Agent):
    name = "Requirement Analyst"
    produces = "qa_requirement/1"

    def __init__(self, spec: dict[str, Any]):
        self.spec = spec

    def run(self, board: Board) -> RequirementAnalysis:
        requirements: list[Requirement] = []
        ambiguities: list[Ambiguity] = []
        missing: list[MissingRequirement] = []

        def next_id() -> str:
            return f"REQ-{len(requirements) + 1:03d}"

        for feature in self.spec["features"]:
            fid = feature["id"]
            req_id = next_id()
            endpoint = Endpoint(**feature["endpoint"]) if feature.get("endpoint") else None
            inputs = [InputField(**i) for i in feature.get("inputs", [])]
            errors = [ErrorCase(**e) for e in feature.get("errors", [])]
            success = feature.get("success") or {}
            expected = feature.get("expected_result")
            example = feature.get("valid_example", {})
            business = feature.get("business", {})

            amb, miss = self._check_feature(req_id, feature, endpoint, inputs, errors, success, example)
            ambiguities += amb
            missing += miss
            testable = bool(endpoint and expected and success.get("status")) and not any(
                a.blocking for a in amb
            )

            base = dict(
                feature=fid,
                feature_name=feature["name"],
                actor=feature.get("actor", "user"),
                priority=feature.get("priority", "medium"),
                endpoint=endpoint,
                requires_auth=feature.get("requires_auth", False),
                inputs=inputs,
                valid_example=example,
                success_status=success.get("status"),
                success_body=success.get("body", {}),
                success_keys=success.get("body_keys", []),
                errors=errors,
                business=business,
            )
            requirements.append(
                Requirement(
                    id=req_id,
                    type="functional",
                    behavior=feature.get("description", ""),
                    expected_result=expected,
                    testable=testable,
                    source_ref=f"features[{fid}]",
                    **base,
                )
            )

            for i, raw_rule in enumerate(feature.get("rules", [])):
                rule = BusinessRule(**raw_rule)
                rid = next_id()
                rule_amb = self._check_rule(rid, rule)
                ambiguities += rule_amb
                requirements.append(
                    Requirement(
                        id=rid,
                        type="business_rule",
                        behavior=rule.description,
                        expected_result=rule.description,
                        rule=rule,
                        parent=req_id,
                        testable=testable and not any(a.blocking for a in rule_amb),
                        source_ref=f"features[{fid}].rules[{i}]",
                        **base,
                    )
                )

            for key, text in (feature.get("non_functional") or {}).items():
                nid = next_id()
                limit = _threshold_ms(text)
                if limit is None:
                    ambiguities.append(Ambiguity(
                        req_id=nid, field=f"non_functional.{key}",
                        issue="정량 기준이 없어 합격/불합격을 판정할 수 없음 (목표 응답시간 필요)",
                        quote=text,
                    ))
                requirements.append(
                    Requirement(
                        id=nid,
                        type="non_functional",
                        behavior=text,
                        expected_result=f"응답시간 {limit}ms 이내" if limit else None,
                        max_response_ms=limit,
                        parent=req_id,
                        testable=testable,
                        source_ref=f"features[{fid}].non_functional.{key}",
                        **base,
                    )
                )

        return RequirementAnalysis(
            product=self.spec["product"],
            base_url=self.spec["base_url"],
            auth=self.spec.get("auth"),
            reset=Endpoint(**self.spec["reset"]) if self.spec.get("reset") else None,
            health=Endpoint(**self.spec["health"]) if self.spec.get("health") else None,
            requirements=requirements,
            ambiguities=ambiguities,
            missing_requirements=missing,
            testable=all(r.testable for r in requirements),
        )

    def _check_feature(self, req_id, feature, endpoint, inputs, errors, success, example):
        amb: list[Ambiguity] = []
        miss: list[MissingRequirement] = []

        for field in ("description", "expected_result"):
            text = feature.get(field) or ""
            for term in _vague_terms(text):
                amb.append(Ambiguity(
                    req_id=req_id, field=field,
                    issue=f"모호한 표현 '{term}' — 검증 가능한 기준으로 바꿔야 함",
                    quote=text,
                ))
        if not feature.get("expected_result"):
            amb.append(Ambiguity(
                req_id=req_id, field="expected_result",
                issue="기대 결과가 정의되지 않아 테스트 오라클을 만들 수 없음", blocking=True,
            ))
        if endpoint is None:
            miss.append(MissingRequirement(
                req_id=req_id, category="interface",
                description="관찰 가능한 인터페이스(API/화면)가 정의되지 않음",
            ))
        if endpoint is not None and not success.get("status"):
            miss.append(MissingRequirement(
                req_id=req_id, category="success_criteria",
                description="성공 응답(status/본문)이 정의되지 않음",
            ))

        has_validation = any(e.when == "validation" for e in errors)
        if inputs and not has_validation:
            miss.append(MissingRequirement(
                req_id=req_id, category="error_handling",
                description="입력 검증 실패 시의 응답이 정의되지 않음",
            ))
        if feature.get("requires_auth") and not any(
            e.status == 401 and not e.input for e in errors
        ):
            miss.append(MissingRequirement(
                req_id=req_id, category="auth_error",
                description="인증 없이 호출했을 때의 응답이 정의되지 않음",
            ))
        for f in inputs:
            if f.type in ("string", "email") and f.max_length is None:
                miss.append(MissingRequirement(
                    req_id=req_id, category="boundary",
                    description=f"입력 '{f.name}'의 최대 길이가 정의되지 않음",
                ))
            if f.type in ("integer", "number") and (f.minimum is None or f.maximum is None):
                miss.append(MissingRequirement(
                    req_id=req_id, category="boundary",
                    description=f"입력 '{f.name}'의 허용 범위가 정의되지 않음",
                ))
            if f.name not in example:
                miss.append(MissingRequirement(
                    req_id=req_id, category="test_data",
                    description=f"입력 '{f.name}'의 유효한 예시 값이 없음",
                ))
        return amb, miss

    def _check_rule(self, req_id: str, rule: BusinessRule) -> list[Ambiguity]:
        amb = [
            Ambiguity(req_id=req_id, field="rule.description",
                      issue=f"모호한 표현 '{t}'", quote=rule.description)
            for t in _vague_terms(rule.description)
        ]
        if rule.kind == "threshold_lock" and (rule.threshold is None or rule.status is None):
            amb.append(Ambiguity(
                req_id=req_id, field="rule",
                issue="잠금 임계값 또는 잠금 후 응답이 정의되지 않음", blocking=True,
            ))
        if rule.kind == "idempotent" and (not rule.header or not rule.key):
            amb.append(Ambiguity(
                req_id=req_id, field="rule",
                issue="멱등성 키 헤더 또는 비교할 응답 필드가 정의되지 않음", blocking=True,
            ))
        return amb
