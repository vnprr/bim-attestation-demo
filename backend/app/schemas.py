"""Data shapes shared by the QA engine, the chain client and the API."""

from pathlib import Path

from pydantic import BaseModel, Field


class Ruleset(BaseModel):
    name: str
    hash: str
    path: Path = Field(exclude=True)


class Violation(BaseModel):
    rule: str
    global_id: str
    element: str
    reason: str


class QaResult(BaseModel):
    """Exactly what `result_hash` commits to: no timestamps, paths or filenames."""

    engine: str
    asset_hash: str
    ruleset_hash: str
    passed: bool
    violations: list[Violation]


class QaReport(BaseModel):
    ruleset_name: str
    result: QaResult
    result_hash: str


class Milestone(BaseModel):
    """The on-chain `Milestone` account, decoded. Hashes are hex strings."""

    address: str
    investor: str
    contractor: str
    oracle: str
    arbiter: str
    amount: int
    ruleset_hash: str
    deadline: int
    dispute_window: int
    status: str
    approved_at: int
    disputed_at: int
    asset_hash: str
    result_hash: str
    milestone_id: int


class Tx(BaseModel):
    signature: str
    ok: bool
    error: str | None = None
    logs: list[str] = []


class MilestoneView(BaseModel):
    milestone: Milestone
    ruleset_name: str | None
    ruleset_file: str | None  # e.g. ruleset_a_strict.ids, for the `reproduce` command
    balances: dict[str, int]
    now: int
    window_ends_at: int | None  # Approved/Disputed: when the payment becomes claimable


class ActionResponse(BaseModel):
    """Every state-changing endpoint returns the fresh on-chain view plus what happened."""

    view: MilestoneView
    tx: Tx | None = None
    qa: QaReport | None = None
    note: str | None = None  # plain words: why nothing was sent, or what happens next


class ClusterConfig(BaseModel):
    cluster: str
    explorer_query: str


class Health(BaseModel):
    cluster: str
    balances: dict[str, int]
    low: list[str]


class CreateRequest(BaseModel):
    amount_sol: float = Field(gt=0, le=100)
    deadline_seconds: int = Field(gt=0, le=7 * 24 * 3600)
    dispute_window_seconds: int = Field(ge=10, le=7 * 24 * 3600)  # same bounds as the program
    ruleset_hash: str


class ResolveRequest(BaseModel):
    pay_contractor: bool
