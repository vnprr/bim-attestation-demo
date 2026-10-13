"""The full demo scenario through the API against a running validator (scripts/localnet.sh).

Also proves the hand-written parts of chain.py (PDA seeds, instruction encoding,
account decoding) match the real program. Manual devnet check (needs funded keys,
scripts/devnet_deploy.sh): CLUSTER=devnet uv run pytest tests/test_flow_localnet.py
"""

import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import CLUSTER, ROOT, RPC_URL

SOL = 1_000_000_000
FEE = 5_000
WINDOW = 10  # the program's minimum dispute window keeps the test short
DEMO = ROOT / "demo"


def validator_running() -> bool:
    try:
        return httpx.post(RPC_URL, json={"jsonrpc": "2.0", "id": 1, "method": "getHealth"}, timeout=1).is_success
    except httpx.HTTPError:
        return False


pytestmark = [pytest.mark.localnet, pytest.mark.skipif(not validator_running(), reason="no local validator")]


@pytest.fixture(scope="module")
def api():
    from app.main import app  # needs the built program IDL and the demo keys

    with TestClient(app) as client:
        yield client


def call(api: TestClient, path: str, ifc: str | None = None, **kwargs) -> dict:
    files = {"file": (ifc, (DEMO / ifc).read_bytes())} if ifc else None
    response = api.post(f"/api{path}", files=files, **kwargs)
    assert response.status_code == 200, response.text
    return response.json()


def create(api: TestClient, deadline_seconds: int = 300) -> tuple[str, dict]:
    strict = next(r["hash"] for r in api.get("/api/rulesets").json() if r["name"].endswith("Strict"))
    request = {"amount_sol": 1, "deadline_seconds": deadline_seconds, "dispute_window_seconds": WINDOW, "ruleset_hash": strict}
    created = call(api, "/milestones", json=request)
    assert created["tx"]["ok"]
    return created["view"]["milestone"]["address"], created["view"]


def wait_until_after(api: TestClient, address: str, moment: int) -> dict:
    """Waits for the chain's clock (not ours) to pass `moment`; returns the fresh view."""
    while (view := api.get(f"/api/milestones/{address}").json())["now"] <= moment:
        time.sleep(0.5)
    return view


def test_scenario_fail_attack_approve_claim(api):
    address, view = create(api)
    assert view["milestone"]["status"] == "Open"
    contractor_before = view["balances"]["contractor"]

    broken = call(api, f"/milestones/{address}/submit", ifc="architecture_broken.ifc")
    assert not broken["qa"]["result"]["passed"]
    assert broken["tx"] is None
    assert broken["view"]["balances"]["contractor"] == contractor_before

    lenient = call(api, f"/milestones/{address}/attack/lenient-ruleset", ifc="architecture_broken.ifc")
    assert lenient["qa"]["result"]["passed"]  # the easier rules would accept the broken model…
    assert lenient["tx"]["error"] == "RulesetMismatch"  # …but the program refuses
    assert lenient["view"]["milestone"]["status"] == "Open"

    valid = call(api, f"/milestones/{address}/submit", ifc="architecture_valid.ifc")
    assert valid["qa"]["result"]["passed"] and valid["tx"]["ok"]
    on_chain = valid["view"]["milestone"]
    assert on_chain["status"] == "Approved"
    assert on_chain["asset_hash"] == valid["qa"]["result"]["asset_hash"]
    assert on_chain["result_hash"] == valid["qa"]["result_hash"]
    assert valid["view"]["window_ends_at"] == on_chain["approved_at"] + WINDOW
    assert valid["view"]["balances"]["contractor"] == contractor_before  # approval moves no money

    early = call(api, f"/milestones/{address}/claim")
    assert early["tx"]["error"] == "ClaimTooEarly"

    wait_until_after(api, address, valid["view"]["window_ends_at"])
    paid = call(api, f"/milestones/{address}/claim")
    assert paid["tx"]["ok"]
    assert paid["view"]["milestone"]["status"] == "Released"
    assert paid["view"]["balances"]["contractor"] == contractor_before + SOL

    again = call(api, f"/milestones/{address}/claim")
    assert again["tx"]["error"] == "NotApproved"
    assert again["view"]["balances"]["contractor"] == contractor_before + SOL


@pytest.mark.parametrize("pay_contractor", [True, False], ids=["arbiter-pays-contractor", "arbiter-refunds-investor"])
def test_dispute_decided_by_arbiter(api, pay_contractor):
    address, _ = create(api)
    assert call(api, f"/milestones/{address}/submit", ifc="architecture_valid.ifc")["tx"]["ok"]

    disputed = call(api, f"/milestones/{address}/dispute")
    assert disputed["tx"]["ok"]
    assert disputed["view"]["milestone"]["status"] == "Disputed"
    before = disputed["view"]["balances"]

    resolved = call(api, f"/milestones/{address}/resolve", json={"pay_contractor": pay_contractor})
    assert resolved["tx"]["ok"]
    after = resolved["view"]["balances"]
    winner = "contractor" if pay_contractor else "investor"
    assert resolved["view"]["milestone"]["status"] == ("Released" if pay_contractor else "Refunded")
    assert after[winner] == before[winner] + SOL  # the arbiter paid the fee

    assert call(api, f"/milestones/{address}/claim")["tx"]["error"] == "NotApproved"


def test_refund_after_deadline(api):
    address, view = create(api, deadline_seconds=10)  # long enough for devnet confirmation times
    locked = view["balances"]["milestone"]

    early = call(api, f"/milestones/{address}/refund")
    assert early["tx"]["error"] == "DeadlineNotReached"

    view = wait_until_after(api, address, view["milestone"]["deadline"])
    refunded = call(api, f"/milestones/{address}/refund")
    assert refunded["tx"]["ok"]
    assert refunded["view"]["milestone"]["status"] == "Refunded"
    assert refunded["view"]["balances"]["investor"] == view["balances"]["investor"] + SOL - FEE
    assert refunded["view"]["balances"]["milestone"] == locked - SOL  # rent-exempt reserve stays

    late = call(api, f"/milestones/{address}/submit", ifc="architecture_valid.ifc")
    assert late["tx"] is None and late["note"] == "Milestone is already Refunded"


def test_config_and_health(api):
    assert api.get("/api/config").json()["cluster"] == CLUSTER
    health = api.get("/api/health").json()
    assert set(health["balances"]) == {"investor", "contractor", "oracle", "arbiter"}
    assert health["low"] == []  # every fee payer can pay


def test_unknown_milestone_is_404(api):
    assert api.get("/api/milestones/11111111111111111111111111111111").status_code == 404
