"""Phase 3G — Evidence Navigator.

USER QUESTION -> (Claude tool selection | deterministic router) -> RATIO BACKEND
-> STRUCTURED EVIDENCE -> (Claude explanation | deterministic fallback) -> ANSWER

The navigator is strictly read-only. It cannot modify weights, thresholds,
mission policy, or analysis results. Every request is audit-logged.
"""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.core.config import ROOT, DATA_DIR
from backend.app.services import evidence_api
from backend.app.services.llm_client import LLMClient, LLMUnavailableError
from ratio_core.explain import build_fallback_explanation

AUDIT_DIR = DATA_DIR / "navigator_audit"

TOOLS = {
    "get_analysis_summary": lambda **a: evidence_api.get_analysis_summary(a["analysis_id"]),
    "get_feature_evidence": lambda **a: evidence_api.get_feature_evidence(a["feature_id"], a.get("analysis_id")),
    "get_dem_support": lambda **a: evidence_api.get_dem_support(a["feature_id"], a.get("analysis_id")),
    "get_registration": lambda **a: evidence_api.get_registration(a.get("analysis_id"), a.get("feature_id")),
    "get_processing_passport": lambda **a: evidence_api.get_processing_passport(a["analysis_id"]),
    "compare_features": lambda **a: evidence_api.compare_features(a["feature_a"], a["feature_b"], a.get("analysis_id")),
    "get_region_summary": lambda **a: evidence_api.get_region_summary(a["analysis_id"], a.get("region", "ALL")),
    "get_mission_decision": lambda **a: evidence_api.get_mission_decision(a.get("analysis_id"), a.get("feature_id")),
    "get_benchmark_summary": lambda **a: evidence_api.get_benchmark_summary(),
    "get_model_drift_report": lambda **a: evidence_api.get_model_drift_report(),
}

TOOL_SCHEMAS = [
    {"name": "get_analysis_summary", "description": "Compact summary of one analysis run.", "parameters": {"analysis_id": "str"}},
    {"name": "get_feature_evidence", "description": "Full structured evidence for one feature.", "parameters": {"feature_id": "str", "analysis_id": "str (optional)"}},
    {"name": "get_dem_support", "description": "DEM/physical support components for one feature.", "parameters": {"feature_id": "str", "analysis_id": "str (optional)"}},
    {"name": "get_registration", "description": "Registration record including independent validation residuals.", "parameters": {"analysis_id": "str", "feature_id": "str (optional)"}},
    {"name": "get_processing_passport", "description": "Processing passport with hashes and provenance.", "parameters": {"analysis_id": "str"}},
    {"name": "compare_features", "description": "Backend-computed comparison of two features.", "parameters": {"feature_a": "str", "feature_b": "str", "analysis_id": "str (optional)"}},
    {"name": "get_region_summary", "description": "Summary over all regions or one region of an analysis.", "parameters": {"analysis_id": "str", "region": "str (default ALL)"}},
    {"name": "get_mission_decision", "description": "The deterministic mission-policy decision.", "parameters": {"analysis_id": "str", "feature_id": "str (optional)"}},
    {"name": "get_benchmark_summary", "description": "Latest synthetic-benchmark results.", "parameters": {}},
    {"name": "get_model_drift_report", "description": "Latest enhancement drift report.", "parameters": {}},
]

MUTATION_PATTERN = re.compile(
    r"\b(approve|override|change|modify|alter|set|reset|edit|update|bypass|force|whitelist|"
    r"mark as safe|make it safe|export anyway|lower|raise)\b", re.IGNORECASE)
FEATURE_PATTERN = re.compile(r"\bF\d{2,3}\b", re.IGNORECASE)


def _phase3_config() -> dict:
    return json.loads((ROOT / "configs" / "phase3.json").read_text())


def _llm_client() -> LLMClient:
    return LLMClient(_phase3_config()["llm"])


def _audit(entry: dict) -> str:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry_id = hashlib.sha256(json.dumps(entry, sort_keys=True, default=str).encode()).hexdigest()[:16]
    entry = {"audit_id": entry_id, **entry}
    with (AUDIT_DIR / f"navigator_audit_{day}.jsonl").open("a") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry_id


def _tool_result_ids(results: dict[str, Any]) -> dict[str, str]:
    return {name: hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:16]
            for name, value in results.items()}


def route_question(question: str, analysis_id: str | None, feature_id: str | None) -> tuple[str, list[dict]]:
    """Deterministic intent router — used offline and as a fallback."""
    q = question or ""
    lower = q.lower()
    feature_ids = FEATURE_PATTERN.findall(q)
    active_feature = feature_id or (feature_ids[0].upper() if feature_ids else None)
    if MUTATION_PATTERN.search(q) and not any(k in lower for k in ("what", "why", "compare", "show", "list", "summarize")):
        return "policy_immutability", [{"tool": "get_mission_decision",
                                        "args": {"analysis_id": analysis_id, "feature_id": active_feature}}]
    if re.search(r"compare", lower):
        pair = feature_ids[:2]
        if len(pair) == 2:
            return "compare", [{"tool": "compare_features",
                                "args": {"feature_a": pair[0].upper(), "feature_b": pair[1].upper(),
                                         "analysis_id": analysis_id}}]
        if len(pair) == 1 and active_feature and active_feature.upper() != pair[0].upper():
            return "compare", [{"tool": "compare_features",
                                "args": {"feature_a": active_feature.upper(), "feature_b": pair[0].upper(),
                                         "analysis_id": analysis_id}}]
    if any(k in lower for k in ("show all", "which ", "list ")) and "review" in lower:
        return "show_review", [{"tool": "get_region_summary", "args": {"analysis_id": analysis_id, "region": "ALL"}}]
    if ("weak dem" in lower or "weak terrain" in lower or "dem support" in lower) and any(
            k in lower for k in ("region", "which", "where", "show")):
        return "weak_dem", [{"tool": "get_region_summary", "args": {"analysis_id": analysis_id, "region": "ALL"}}]
    if any(k in lower for k in ("registration", "aligned", "alignment")) and analysis_id:
        return "registration", [{"tool": "get_registration",
                                 "args": {"analysis_id": analysis_id, "feature_id": active_feature}}]
    if any(k in lower for k in ("benchmark", "synthetic range", "test range")):
        return "benchmark", [{"tool": "get_benchmark_summary", "args": {}}]
    if any(k in lower for k in ("drift", "governance", "enhancer version")):
        return "drift", [{"tool": "get_model_drift_report", "args": {}}]
    if any(k in lower for k in ("missing", "confidence", "what would", "increase")):
        plan = []
        if active_feature:
            plan += [{"tool": "get_feature_evidence",
                      "args": {"feature_id": active_feature, "analysis_id": analysis_id}},
                     {"tool": "get_dem_support",
                      "args": {"feature_id": active_feature, "analysis_id": analysis_id}}]
        plan.append({"tool": "get_registration", "args": {"analysis_id": analysis_id, "feature_id": active_feature}})
        return "missing_evidence", plan
    if active_feature:
        return "why_feature", [
            {"tool": "get_feature_evidence", "args": {"feature_id": active_feature, "analysis_id": analysis_id}},
            {"tool": "get_mission_decision", "args": {"analysis_id": analysis_id, "feature_id": active_feature}},
        ]
    if any(k in lower for k in ("decision", "blocked", "export", "safe", "mission")) and analysis_id:
        return "decision", [{"tool": "get_mission_decision",
                             "args": {"analysis_id": analysis_id, "feature_id": active_feature}}]
    if analysis_id:
        return "summarize", [
            {"tool": "get_analysis_summary", "args": {"analysis_id": analysis_id}},
            {"tool": "get_region_summary", "args": {"analysis_id": analysis_id, "region": "ALL"}},
        ]
    return "summarize", [{"tool": "get_benchmark_summary", "args": {}}]


def execute_tool_calls(tool_calls: list[dict]) -> dict[str, Any]:
    """Whitelisted, read-only execution of tool calls."""
    results: dict[str, Any] = {}
    for call in tool_calls:
        name = call.get("tool") or call.get("name")
        if name not in TOOLS:
            results[f"REJECTED_{name}"] = {"error": "UNKNOWN_OR_FORBIDDEN_TOOL",
                                           "message": "Only read-only RATIO evidence tools are available."}
            continue
        try:
            args = {k: v for k, v in (call.get("args") or {}).items() if v not in (None, "")}
            results[name] = TOOLS[name](**args)
        except (FileNotFoundError, ValueError, KeyError) as exc:
            results[name] = {"error": str(exc), "message": "Evidence unavailable for this query."}
    return results


def _fmt(value, digits: int = 3) -> str:
    if value is None:
        return "unavailable"
    return f"{value:.{digits}f}" if isinstance(value, float) else str(value)


def _navigator_fallback(question: str, intent: str, tool_results: dict[str, Any],
                        analysis_id: str | None, feature_id: str | None) -> dict[str, Any]:
    """Deterministic explanation when Claude is unavailable or invalid."""
    feature = None
    for value in tool_results.values():
        if isinstance(value, dict) and isinstance(value.get("feature"), dict):
            feature = value["feature"]
            break
    policy = None
    for value in tool_results.values():
        if isinstance(value, dict) and value.get("policy_decision") and "mission_profile" in value:
            policy = {"decision": value.get("policy_decision"), "mission_profile": value.get("mission_profile"),
                      "reason_codes": value.get("reason_codes")}
            break
    analysis_summary = next((v for v in tool_results.values()
                             if isinstance(v, dict) and "compatibility_score" in v and "region_count" in v), None)
    registration = next((v.get("registration") for v in tool_results.values()
                         if isinstance(v, dict) and "registration" in v), None)
    if intent == "policy_immutability":
        decision = (policy or {}).get("decision", "REVIEW_REQUIRED")
        return {"executive_summary": "The Evidence Navigator cannot change scientific state.",
                "risk_assessment": "No risk values were modified by this request.",
                "evidence_explanation": "Weights, thresholds, mission policy, and analysis results are immutable "
                                        "through the assistant. The request was treated as a read-only question.",
                "recommendation": f"The recorded deterministic policy decision remains {decision}.",
                "limitations": ["Navigator permissions are read-only by design.",
                                "Administrator workflows for policy changes are not part of this prototype."]}
    if intent == "compare":
        comparison = next((v.get("comparison") for v in tool_results.values()
                           if isinstance(v, dict) and "comparison" in v), {})
        a = next((v.get("feature_a", {}).get("feature_id") for v in tool_results.values()
                  if isinstance(v, dict) and "feature_a" in v), "A")
        b = next((v.get("feature_b", {}).get("feature_id") for v in tool_results.values()
                  if isinstance(v, dict) and "feature_b" in v), "B")
        vd = comparison.get("visual_change_difference")
        pd = comparison.get("physical_support_difference")
        rd = comparison.get("risk_difference")
        return {"executive_summary": f"Backend comparison of {a} and {b}.",
                "risk_assessment": f"Unsupported-risk difference is {_fmt(rd)} (backend-computed).",
                "evidence_explanation": f"Visual-change difference is {_fmt(vd)}; "
                                        f"physical-support difference is {_fmt(pd)}; "
                                        f"unsupported-risk difference is {_fmt(rd)}. "
                                        f"Physical status pair: {comparison.get('physical_status_pair')}.",
                "recommendation": "Differences are computed by the RATIO backend, not inferred by the assistant.",
                "limitations": ["Comparison is limited to structured evidence fields.",
                                "A None difference means one side had no value recorded."]}
    if intent == "missing_evidence":
        missing = []
        if feature is not None:
            components = feature.get("support_components") or {}
            for name, value in components.items():
                if value is None:
                    missing.append(name)
            if feature.get("physical_support") is None:
                missing.append("physical_support")
        return {"executive_summary": "Evidence inventory for the selected feature.",
                "risk_assessment": "Missing components reduce, never fabricate, physical support.",
                "evidence_explanation": f"Missing or unavailable evidence: {missing or 'none recorded'}. "
                                        f"RATIO omits unavailable evidence instead of treating it as zero.",
                "recommendation": "To increase evidence quality: add acquisition illumination metadata "
                                  "(enables hillshade comparison), an independent validation point "
                                  "(tests the affine transform), and a higher-resolution reference where "
                                  "the current one is too coarse.",
                "limitations": ["The assistant lists what the backend reported unavailable.",
                                "It cannot estimate what missing evidence would have shown."]}
    if intent in {"show_review", "weak_dem"}:
        summary = next((v for v in tool_results.values()
                        if isinstance(v, dict) and "feature_count" in v), {})
        key = ("weak_dem_support_feature_ids" if intent == "weak_dem" else "review_required_feature_ids")
        ids = summary.get(key, [])
        return {"executive_summary": f"{len(ids)} region(s) matched the query.",
                "risk_assessment": "The mission decision for this analysis is unchanged by this query.",
                "evidence_explanation": f"Region IDs: {ids or 'none'}. "
                                        f"Decision context: {summary.get('policy_decision')}.",
                "recommendation": "Inspect the listed regions in the evidence chain view for the recorded reason codes.",
                "limitations": ["Only regions recorded by the deterministic backend are listed."]}
    if intent == "registration" and registration:
        return {"executive_summary": "Registration record for the selected analysis.",
                "risk_assessment": f"Registration quality {_fmt(registration.get('quality_score'))} "
                                   f"({registration.get('quality_label')}).",
                "evidence_explanation": (f"Method {registration.get('method')}; fit RMSE "
                                         f"{_fmt(registration.get('rmse_px'))} px; basis "
                                         f"{registration.get('validation_basis')}; independent validation RMSE "
                                         f"{_fmt(registration.get('validation_rmse_px'))} px over "
                                         f"{registration.get('validation_point_count', 0)} point(s)."),
                "recommendation": "A zero fit RMSE with three control points is not proof of correctness; "
                                  "the independent validation point is the test.",
                "limitations": ["Affine transform only; no perspective or camera-model registration."]}
    analysis = {"mission_profile": (policy or {}).get("mission_profile"),
                "comparison_status": (analysis_summary or {}).get("comparison_status")}
    report = build_fallback_explanation(analysis, feature, registration, policy)
    report["evidence_explanation"] = (f"Question: {question}\n" + report["evidence_explanation"])
    return report


async def answer_query(question: str, analysis_id: str | None = None,
                       feature_id: str | None = None) -> dict[str, Any]:
    """Full navigator flow: intent -> tools -> evidence -> explanation."""
    config = _phase3_config()
    intent, tool_calls = route_question(question, analysis_id, feature_id)
    tool_results = execute_tool_calls(tool_calls[:int(config["navigator"]["max_tool_calls_per_query"])])
    llm = _llm_client()
    model_identifier = llm.identifier() if llm.available else "deterministic-offline"
    used_llm = False
    fallback_used = False
    report = None
    if llm.available and not intent == "policy_immutability":
        used_llm = True
        try:
            payload = {
                "question": question,
                "tool_results": tool_results,
            }
            explanation = await llm.explain_evidence(payload)
            report = dict(explanation)
        except LLMUnavailableError:
            fallback_used = True
            report = _navigator_fallback(question, intent, tool_results, analysis_id, feature_id)
    else:
        fallback_used = True
        report = _navigator_fallback(question, intent, tool_results, analysis_id, feature_id)
    # The deterministic decision is attached by the BACKEND, never by the LLM.
    decision = next((v for v in tool_results.values()
                     if isinstance(v, dict) and v.get("policy_decision")), None)
    final = {
        "question": question,
        "analysis_id": analysis_id,
        "feature_id": feature_id,
        "intent": intent,
        "tools_called": [c.get("tool") for c in tool_calls],
        "tool_result_ids": _tool_result_ids(tool_results),
        "tool_results": tool_results,
        "explanation": report,
        "model_identifier": model_identifier,
        "llm_used": used_llm,
        "fallback_used": fallback_used,
        "immutable_state_note": "Scientific state was not modified by this query.",
    }
    if decision:
        final["policy_decision"] = decision.get("policy_decision")
        final["explanation"]["policy_decision"] = decision.get("policy_decision")
    _audit({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "analysis_id": analysis_id,
        "feature_id": feature_id,
        "user_question": question[:500],
        "intent": intent,
        "tools_called": [c.get("tool") for c in tool_calls],
        "tool_result_ids": final["tool_result_ids"],
        "model_identifier": model_identifier,
        "response_status": "OK",
        "fallback_used": fallback_used,
    })
    return final


def list_audit(limit: int = 50) -> dict:
    entries = []
    if AUDIT_DIR.exists():
        for path in sorted(AUDIT_DIR.glob("*.jsonl")):
            for line in path.read_text().splitlines():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return {"count": len(entries), "entries": entries[:limit]}
