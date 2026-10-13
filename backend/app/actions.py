"""What each demo action does. The oracle lives here: it takes the ruleset from the chain,
runs QA and only on PASS signs an approval. Where money goes is decided on chain:
claim, dispute, resolve and refund are sent as they are, and the program accepts or rejects them."""

import asyncio

from . import chain, config
from .qa import load_ruleset, load_rulesets, run_qa
from .schemas import ActionResponse, ClusterConfig, CreateRequest, Health, Milestone, MilestoneView, Ruleset

LAMPORTS_PER_SOL = 1_000_000_000
ROLES = ("investor", "contractor", "oracle", "arbiter")
FEE_PAYERS = ("investor", "oracle", "arbiter")  # the contractor never signs, so it may hold 0 SOL
RULESETS = load_rulesets(config.RULES_DIR)
LENIENT = load_ruleset(config.RULES_DIR / "ruleset_b_lenient.ids")


def cluster_config() -> ClusterConfig:
    return ClusterConfig(cluster=config.CLUSTER, explorer_query=config.EXPLORER_QUERY)


async def health() -> Health:
    """Balances of the demo keys. On devnet a fee payer can run dry; the UI warns before that happens."""
    balances = await chain.balances({role: str(chain.keypair(role).pubkey()) for role in ROLES})
    low = [role for role in FEE_PAYERS if balances[role] < config.LOW_BALANCE]
    return Health(cluster=config.CLUSTER, balances=balances, low=low)


async def get_milestone(address: str) -> Milestone:
    try:
        milestone = await chain.read_milestone(address)
    except ValueError as error:  # not a base58 public key
        raise ValueError(f"Invalid address: {address}") from error
    if milestone is None:
        raise LookupError(f"No milestone account at {address}")
    return milestone


async def view(address: str) -> MilestoneView:
    """Everything the UI shows, read from the chain."""
    m = await get_milestone(address)
    ruleset = RULESETS.get(m.ruleset_hash)
    return MilestoneView(
        milestone=m,
        ruleset_name=ruleset.name if ruleset else None,
        ruleset_file=ruleset.path.name if ruleset else None,
        balances=await chain.balances({"investor": m.investor, "contractor": m.contractor, "milestone": m.address}),
        now=await chain.chain_time(),
        window_ends_at=window_end(m),
    )


def window_end(m: Milestone) -> int | None:
    """Mirrors `claim` in the program: after this time the payment can be claimed."""
    if m.status == "Approved":
        return m.approved_at + m.dispute_window
    if m.status == "Disputed":
        return m.disputed_at + m.dispute_window
    return None


async def create(request: CreateRequest) -> ActionResponse:
    if request.ruleset_hash not in RULESETS:
        raise ValueError("Unknown ruleset")
    deadline = await chain.chain_time() + request.deadline_seconds
    lamports = round(request.amount_sol * LAMPORTS_PER_SOL)
    address, tx = await chain.create_milestone(lamports, request.ruleset_hash, deadline, request.dispute_window_seconds)
    if tx.error == "Custom(1)":  # system program: insufficient lamports for amount + account rent
        raise ValueError("create_milestone rejected: the investor does not have enough SOL for this amount")
    if not tx.ok:
        raise ValueError(f"create_milestone rejected: {tx.error}")
    return ActionResponse(view=await view(address), tx=tx)


async def submit(address: str, ifc_bytes: bytes) -> ActionResponse:
    """Contractor uploads a model. The oracle checks it against the ruleset frozen on chain."""
    m = await get_milestone(address)
    if m.status != "Open":
        return ActionResponse(view=await view(address), note=f"Milestone is already {m.status}")
    if await chain.chain_time() > m.deadline:
        return ActionResponse(view=await view(address), note="Deadline has passed")
    ruleset = RULESETS.get(m.ruleset_hash)
    if ruleset is None:
        return ActionResponse(view=await view(address), note="The oracle does not know the ruleset frozen on chain")
    return await _qa_then_approve(m, ifc_bytes, ruleset)


async def attack_lenient_ruleset(address: str, ifc_bytes: bytes) -> ActionResponse:
    """Attack: pass QA with an easier ruleset than the frozen one. The program must reject it."""
    m = await get_milestone(address)
    if m.ruleset_hash == LENIENT.hash:
        return ActionResponse(view=await view(address), note="This milestone already uses the lenient ruleset")
    return await _qa_then_approve(m, ifc_bytes, LENIENT)


async def claim(address: str) -> ActionResponse:
    """Too early, already paid, or never approved: the program rejects it, not us."""
    tx = await chain.claim(await get_milestone(address))
    return ActionResponse(view=await view(address), tx=tx)


async def dispute(address: str) -> ActionResponse:
    tx = await chain.dispute(await get_milestone(address))
    return ActionResponse(view=await view(address), tx=tx)


async def resolve(address: str, pay_contractor: bool) -> ActionResponse:
    tx = await chain.resolve(await get_milestone(address), pay_contractor)
    return ActionResponse(view=await view(address), tx=tx)


async def refund(address: str) -> ActionResponse:
    tx = await chain.refund(await get_milestone(address))
    return ActionResponse(view=await view(address), tx=tx)


async def _qa_then_approve(m: Milestone, ifc_bytes: bytes, ruleset: Ruleset) -> ActionResponse:
    report = await asyncio.to_thread(run_qa, ifc_bytes, ruleset)
    if not report.result.passed:
        return ActionResponse(
            view=await view(m.address), qa=report, note="QA failed: no transaction sent, funds stay locked"
        )
    tx = await chain.approve(m, report.result.asset_hash, ruleset.hash, report.result_hash)
    note = None
    if tx.ok:
        note = f"The payment is claimable after the {m.dispute_window} s dispute window, unless the investor disputes."
    return ActionResponse(view=await view(m.address), qa=report, tx=tx, note=note)
