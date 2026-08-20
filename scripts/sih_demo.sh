#!/usr/bin/env bash
# RATIO 2.0 — one-command SIH demo runner.
# Boots the backend, builds the frontend, runs the full regression + acceptance
# suites, runs all 8 SIH demo cases server-side, and prints the recorded results.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== [1/5] backend health"
PYTHONPATH=. .venv/bin/python - <<'PYEOF'
import sys
sys.path.insert(0, ".")
from backend.app.main import app
from fastapi.testclient import TestClient
body = TestClient(app).get("/api/health/phase3").json()
print("   ", body)
PYEOF

echo "== [2/5] regression suites"
PYTHONPATH=. .venv/bin/pytest -q 2>&1 | tail -1
PYTHONPATH=. .venv/bin/python scripts/phase2_acceptance.py >/dev/null && echo "    phase2 acceptance: 27/27"
PYTHONPATH=. .venv/bin/python scripts/phase3_acceptance.py >/dev/null && echo "    phase3 acceptance: 14/14"

echo "== [3/5] frontend production build"
(cd frontend && npm run build >/dev/null 2>&1) && echo "    build OK"

echo "== [4/5] SIH demo cases (server-side, real pipeline)"
PYTHONPATH=. .venv/bin/python - <<'PYEOF'
import sys, time
sys.path.insert(0, ".")
from backend.app.services import demo
for case in demo.list_cases():
    t0 = time.time()
    r = demo.run_case(case["id"])
    if case["id"] == "case6_model_drift":
        detail = " | ".join(f"{c['candidate']}={c['decision']}" for c in r["comparisons"])
    elif case["id"] in ("case7_evidence_navigator", "case8_claude_offline"):
        policy = r.get("policy_decision") or (r.get("scientific_state_intact") or {}).get("policy_decision")
        detail = f"fallback={r['fallback_used']} policy={policy}"
    else:
        f = r.get("feature") or {}
        detail = f"status={f.get('status')} risk={f.get('unsupported_risk')} decision={(r.get('policy') or {}).get('decision')}"
    print(f"    {case['id']:<32} {time.time()-t0:5.1f}s  {detail}")
PYEOF

echo "== [5/5] boot the console for the judge"
echo "    backend : PYTHONPATH=. .venv/bin/python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"
echo "    frontend: cd frontend && npm run dev"
echo "    demo UI : open the SIH DEMO page and press VERIFY per case"
echo "SIH demo runner complete."
