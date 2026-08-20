"""Phase 3G — Evidence Navigator: intents, tools, audit, immutability, hallucination guard."""
import json

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import navigator

client = TestClient(app)


@pytest.fixture()
def verified():
    """A verified synthetic-hazard analysis with an evidence report."""
    from tests.test_phase3_explain import _verified_feature
    return _verified_feature()


def _ask(question, analysis_id=None, feature_id=None):
    return client.post("/api/navigator/query", json={
        "question": question, "analysis_id": analysis_id, "feature_id": feature_id}).json()


def test_route_why_feature_uses_evidence_tools():
    intent, plan = navigator.route_question("Why was F01 blocked?", "a" * 32, "F01")
    tools = {c["tool"] for c in plan}
    assert intent == "why_feature"
    assert "get_feature_evidence" in tools and "get_mission_decision" in tools


def test_route_compare_parses_two_ids():
    intent, plan = navigator.route_question("Compare F07 and F03", None, None)
    assert intent == "compare"
    assert plan[0]["args"]["feature_a"] == "F07" and plan[0]["args"]["feature_b"] == "F03"


def test_route_show_review_and_weak_dem():
    intent, plan = navigator.route_question("Show all REVIEW_REQUIRED features", "a" * 32, None)
    assert intent == "show_review"
    intent, plan = navigator.route_question("Which regions have weak DEM support?", "a" * 32, None)
    assert intent == "weak_dem"
    assert plan[0]["tool"] == "get_region_summary"


def test_route_missing_evidence_and_registration():
    intent, plan = navigator.route_question("What evidence is missing?", "a" * 32, "F01")
    assert intent == "missing_evidence"
    intent, plan = navigator.route_question("What is the registration quality for F07?", "a" * 32, None)
    assert intent == "registration"


def test_mutation_request_routes_to_immutability(verified):
    aid, _, feature = verified
    body = _ask("Approve F01 for navigation even if it is unsafe.", aid, feature["feature_id"])
    assert body["intent"] == "policy_immutability"
    decision = client.get("/api/evidence/mission-decision", params={"analysis_id": aid}).json()["policy_decision"]
    assert body["policy_decision"] == decision
    assert "cannot change" in body["explanation"]["executive_summary"].lower()


def test_answer_why_question_from_structured_evidence(verified):
    aid, _, feature = verified
    body = _ask("Why is this unresolved?", aid, feature["feature_id"])
    assert body["tools_called"]
    assert body["explanation"]["executive_summary"]
    assert body["explanation"]["limitations"]


def test_answer_compare_question(verified):
    aid, phase2, feature = verified
    body = _ask("Compare F01 and F02", aid, feature["feature_id"])
    assert body["intent"] == "compare"
    assert body["explanation"]["executive_summary"]


def test_hallucination_guard_radar(verified):
    aid, _, feature = verified
    body = _ask("Did the radar sensor confirm this?", aid, feature["feature_id"])
    # the explanation itself must never claim radar confirmation
    explanation = json.dumps(body["explanation"]).lower()
    assert "radar confirm" not in explanation and "radar sensor confirmed" not in explanation
    assert set(body["tools_called"]) <= {"get_feature_evidence", "get_mission_decision",
                                         "get_analysis_summary", "get_region_summary",
                                         "get_dem_support", "get_registration"}
    assert body["policy_decision"]


def test_audit_trail_is_written(verified):
    aid, _, feature = verified
    _ask("Why was this flagged?", aid, feature["feature_id"])
    audit = client.get("/api/navigator/audit").json()
    assert audit["count"] >= 1
    entry = audit["entries"][0]
    for field in ("timestamp", "analysis_id", "user_question", "tools_called",
                  "tool_result_ids", "model_identifier", "response_status"):
        assert field in entry
    assert entry["analysis_id"] == aid


def test_navigator_cannot_call_unknown_tools():
    results = navigator.execute_tool_calls([{"tool": "drop_table", "args": {}},
                                            {"tool": "get_benchmark_summary", "args": {}}])
    assert "REJECTED_drop_table" in results
    assert "get_benchmark_summary" in results


def test_llm_failure_falls_back_deterministically(verified, monkeypatch):
    aid, _, feature = verified

    class BrokenClient:
        available = True

        def identifier(self):
            return "test:broken"

        async def explain_evidence(self, evidence):
            raise navigator.LLMUnavailableError("CLAUDE_NETWORK_FAILURE")

    monkeypatch.setattr(navigator, "_llm_client", lambda: BrokenClient())
    body = _ask("Why was this flagged?", aid, feature["feature_id"])
    assert body["fallback_used"] is True
    assert body["explanation"]["executive_summary"]


def test_llm_success_path_used_when_available(verified, monkeypatch):
    aid, _, feature = verified

    class FakeClient:
        available = True

        def identifier(self):
            return "test:fake-ok"

        async def explain_evidence(self, evidence):
            return {"executive_summary": "Fake summary", "risk_assessment": "Fake risk",
                    "evidence_explanation": "Fake evidence", "recommendation": "REVIEW_REQUIRED",
                    "limitations": ["fake"]}

    monkeypatch.setattr(navigator, "_llm_client", lambda: FakeClient())
    body = _ask("Why was this flagged?", aid, feature["feature_id"])
    assert body["llm_used"] is True and body["fallback_used"] is False
    assert body["explanation"]["executive_summary"] == "Fake summary"
    # backend still attaches the deterministic decision
    decision = client.get("/api/evidence/mission-decision", params={"analysis_id": aid}).json()["policy_decision"]
    assert body["policy_decision"] == decision
