"""Test Executor — runs the plan against the real system and records evidence.

Results are observations, not opinions: every step stores the exact request,
the response, timing, and each assertion with its expected and actual value.
The full log of each test is written to ``evidence/<test-id>.json``. The
executor does not decide whether a failure is a bug; that is the Defect
Analyst's job.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

from ..contracts import (
    AssertionResult,
    Endpoint,
    Expectation,
    Observation,
    ObservationReport,
    RequirementAnalysis,
    Step,
    StepResult,
    TestCase,
    TestPlan,
)
from .base import Agent, Board

BODY_LIMIT = 2000


class HttpClient:
    def __init__(self, base_url: str, timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def send(self, method: str, path: str, body: Optional[dict] = None,
             query: Optional[dict] = None, headers: Optional[dict] = None) -> dict[str, Any]:
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method.upper())
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status, raw = resp.status, resp.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        text = raw.decode("utf-8", "replace")
        try:
            parsed: Any = json.loads(text) if text else None
        except json.JSONDecodeError:
            parsed = text[:BODY_LIMIT]
        return {"status": status, "body": parsed}


def _check(expect: Expectation, resp: dict, elapsed_ms: float,
           previous: Optional[dict]) -> list[AssertionResult]:
    status, body = resp["status"], resp["body"]
    body_dict = body if isinstance(body, dict) else {}
    out: list[AssertionResult] = []

    def add(kind, expected, actual, passed):
        out.append(AssertionResult(type=kind, expected=expected, actual=actual, passed=passed))

    if not expect.allow_5xx:
        add("no_5xx", "status < 500", status, status < 500)
    if expect.status is not None:
        add("status", expect.status, status, status == expect.status)
    if expect.status_in is not None:
        add("status_in", expect.status_in, status, status in expect.status_in)
    if expect.status_not_in is not None:
        add("status_not_in", expect.status_not_in, status, status not in expect.status_not_in)
    for k, v in expect.body_contains.items():
        add(f"body.{k}", v, body_dict.get(k), body_dict.get(k) == v)
    for k in expect.body_has_keys:
        add(f"body_has.{k}", "present", "present" if k in body_dict else "missing", k in body_dict)
    if expect.max_elapsed_ms is not None:
        add("elapsed_ms", f"<= {expect.max_elapsed_ms}", round(elapsed_ms, 1),
            elapsed_ms <= expect.max_elapsed_ms)
    if expect.same_as_previous:
        key = expect.same_as_previous
        before = (previous or {}).get(key)
        add(f"same_as_previous.{key}", before, body_dict.get(key),
            before is not None and body_dict.get(key) == before)
    return out


class TestExecutor(Agent):
    name = "Test Executor"
    consumes = ("qa_requirement/1", "qa_test_plan/1")
    produces = "qa_observation/1"

    def __init__(self, run_dir: Path, base_url: Optional[str] = None):
        self.run_dir = Path(run_dir)
        self.base_url_override = base_url
        self.analysis: Optional[RequirementAnalysis] = None
        self.client: Optional[HttpClient] = None

    # ------------------------------------------------------------------ #
    def run(self, board: Board) -> ObservationReport:
        self.analysis = board["qa_requirement/1"]
        plan: TestPlan = board["qa_test_plan/1"]
        base_url = self.base_url_override or self.analysis.base_url
        self.client = HttpClient(base_url)
        (self.run_dir / "evidence").mkdir(parents=True, exist_ok=True)

        healthy, health_note = self._health()
        observations = []
        for tc in plan.test_cases:
            if not tc.automated:
                observations.append(Observation(
                    test_id=tc.id, req_id=tc.req_id, status="not_run",
                    expected=tc.oracle, actual="수동 탐색 세션 필요", note=tc.charter))
            elif not healthy:
                observations.append(Observation(
                    test_id=tc.id, req_id=tc.req_id, status="error",
                    expected=tc.oracle, actual="환경 사용 불가", note=health_note))
            else:
                observations.append(self.execute(tc))

        summary = {s: sum(o.status == s for o in observations)
                   for s in ("passed", "failed", "error", "not_run")}
        summary["total"] = len(observations)
        return ObservationReport(
            environment={"base_url": base_url, "healthy": healthy, "health_check": health_note,
                         "isolation": "reset before each test" if self.analysis.reset else "none"},
            summary=summary,
            observations=observations,
        )

    def rerun(self, tc: TestCase) -> Observation:
        """Execute a single case again; used by the Defect Analyst to confirm a failure."""
        return self.execute(tc, attempt=2)

    # ------------------------------------------------------------------ #
    def _health(self) -> tuple[bool, str]:
        health: Optional[Endpoint] = self.analysis.health
        if health is None:
            return True, "health endpoint not specified"
        try:
            resp = self.client.send(health.method, health.path)
        except (urllib.error.URLError, OSError) as e:
            return False, f"{health.method} {health.path} failed: {e}"
        return resp["status"] == 200, f"{health.method} {health.path} -> {resp['status']}"

    def _token(self) -> str:
        auth = self.analysis.auth or {}
        login = auth["login"]
        resp = self.client.send(login["method"], login["path"], body=login.get("body"))
        body = resp["body"] if isinstance(resp["body"], dict) else {}
        token = body.get(auth.get("token_key", "token"))
        if not token:
            raise RuntimeError(f"auth login failed with status {resp['status']}")
        return f"{auth.get('scheme', 'Bearer')} {token}".strip()

    def execute(self, tc: TestCase, attempt: int = 1) -> Observation:
        started = time.perf_counter()
        results: list[StepResult] = []
        status = "passed"
        token: Optional[str] = None
        previous_body: Optional[dict] = None
        try:
            if self.analysis.reset:
                self.client.send(self.analysis.reset.method, self.analysis.reset.path)
            for i, step in enumerate(tc.steps):
                headers = dict(step.headers)
                if step.auth:
                    token = token or self._token()
                    headers[(self.analysis.auth or {}).get("header", "Authorization")] = token
                for it in range(step.repeat):
                    res = self._run_step(i, it, step, headers, previous_body)
                    results.append(res)
                    if res.error:
                        status = "error"
                        break
                    if isinstance(res.response["body"], dict):
                        previous_body = res.response["body"]
                    if not all(a.passed for a in res.assertions):
                        status = "failed"
                        break
                if status != "passed":
                    break
        except (urllib.error.URLError, OSError, RuntimeError) as e:
            status = "error"
            results.append(StepResult(step=len(results), iteration=0, request={}, response=None,
                                      error=str(e), elapsed_ms=0, assertions=[]))

        expected, actual = self._describe(tc, results, status)
        suffix = "" if attempt == 1 else f".attempt{attempt}"
        evidence = f"evidence/{tc.id}{suffix}.json"
        obs = Observation(
            test_id=tc.id, req_id=tc.req_id, status=status, expected=expected, actual=actual,
            step_results=results, evidence=[evidence],
            duration_ms=round((time.perf_counter() - started) * 1000, 1), attempt=attempt,
        )
        (self.run_dir / evidence).write_text(json.dumps(
            {"test_case": tc.model_dump(mode="json"), "observation": obs.model_dump(mode="json")},
            ensure_ascii=False, indent=2))
        return obs

    def _run_step(self, i: int, it: int, step: Step, headers: dict,
                  previous: Optional[dict]) -> StepResult:
        request = {"method": step.method, "path": step.path, "query": step.query,
                   "body": step.body, "headers": {k: ("<redacted>" if k.lower() == "authorization" else v)
                                                  for k, v in headers.items()}}
        t0 = time.perf_counter()
        try:
            resp = self.client.send(step.method, step.path, step.body, step.query, headers)
        except (urllib.error.URLError, OSError) as e:
            return StepResult(step=i, iteration=it, request=request, response=None, error=str(e),
                              elapsed_ms=round((time.perf_counter() - t0) * 1000, 1), assertions=[])
        elapsed = (time.perf_counter() - t0) * 1000
        return StepResult(step=i, iteration=it, request=request, response=resp,
                          elapsed_ms=round(elapsed, 1),
                          assertions=_check(step.expect, resp, elapsed, previous))

    @staticmethod
    def _describe(tc: TestCase, results: list[StepResult], status: str) -> tuple[str, str]:
        if status == "error":
            return tc.oracle, f"실행 오류: {results[-1].error if results else 'unknown'}"
        for r in results:
            for a in r.assertions:
                if not a.passed:
                    where = f"step {r.step + 1}" + (f" (반복 {r.iteration + 1})" if r.iteration else "")
                    return (f"{a.type} = {a.expected}", f"{a.type} = {a.actual} at {where}")
        return tc.oracle, "기대대로 동작"
