"""Solana I/O: the six escrow instructions, the Milestone account and balances.

Instructions are encoded by hand: discriminator from the IDL + little-endian args
in the order of the Rust signature. The account layout mirrors `state.rs::Milestone`.
"""

import json
import secrets
import struct
from functools import cache

from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solana.rpc.models import TxOpts
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.message import MessageV0
from solders.pubkey import Pubkey
from solders.system_program import ID as SYSTEM_PROGRAM
from solders.sysvar import CLOCK
from solders.transaction import VersionedTransaction
from solders.transaction_status import InstructionErrorCustom, TransactionErrorInstructionError

from . import config
from .schemas import Milestone, Tx

IDL = json.loads(config.IDL_PATH.read_text())
PROGRAM_ID = Pubkey.from_string(IDL["address"])
DISCRIMINATOR = {ix["name"]: bytes(ix["discriminator"]) for ix in IDL["instructions"]}
ACCOUNT_DISCRIMINATOR = bytes(next(a for a in IDL["accounts"] if a["name"] == "Milestone")["discriminator"])
ERROR_NAMES = {e["code"]: e["name"] for e in IDL["errors"]}

# investor, contractor, oracle, arbiter, amount, ruleset_hash, deadline, dispute_window, status,
# approved_at, disputed_at, asset_hash, result_hash, milestone_id, bump
MILESTONE_LAYOUT = struct.Struct("<32s32s32s32sQ32sqqBqq32s32sQB")
STATUSES = ("Open", "Approved", "Disputed", "Released", "Refunded")


@cache
def keypair(role: str) -> Keypair:
    """Demo keypairs held by the backend: investor, contractor, oracle, arbiter."""
    return Keypair.from_bytes(json.loads((config.KEYS_DIR / f"{role}.json").read_text()))


def rpc() -> AsyncClient:
    return AsyncClient(config.RPC_URL, commitment=Confirmed)


def milestone_address(investor: Pubkey, milestone_id: int) -> Pubkey:
    seeds = [b"milestone", bytes(investor), struct.pack("<Q", milestone_id)]
    return Pubkey.find_program_address(seeds, PROGRAM_ID)[0]


async def create_milestone(amount: int, ruleset_hash: str, deadline: int, dispute_window: int) -> tuple[str, Tx]:
    investor = keypair("investor")
    milestone_id = secrets.randbits(63)
    address = milestone_address(investor.pubkey(), milestone_id)
    args = struct.pack(
        "<Q32s32sQ32sq32sq",
        milestone_id,
        bytes(keypair("contractor").pubkey()),
        bytes(keypair("oracle").pubkey()),
        amount,
        bytes.fromhex(ruleset_hash),
        deadline,
        bytes(keypair("arbiter").pubkey()),
        dispute_window,
    )
    accounts = [_writable(investor.pubkey(), signer=True), _writable(address), AccountMeta(SYSTEM_PROGRAM, False, False)]
    return str(address), await _send("create_milestone", args, accounts, investor)


async def approve(milestone: Milestone, asset_hash: str, ruleset_hash: str, result_hash: str) -> Tx:
    """Signed by the oracle. Opens the dispute window; no money moves."""
    oracle = keypair("oracle")
    args = b"".join(bytes.fromhex(h) for h in (asset_hash, ruleset_hash, result_hash))
    accounts = [AccountMeta(oracle.pubkey(), True, False), _writable(_key(milestone.address))]
    return await _send("approve", args, accounts, oracle)


async def dispute(milestone: Milestone) -> Tx:
    investor = keypair("investor")
    accounts = [AccountMeta(investor.pubkey(), True, False), _writable(_key(milestone.address))]
    return await _send("dispute", b"", accounts, investor)


async def resolve(milestone: Milestone, pay_contractor: bool) -> Tx:
    """Signed by the arbiter. The program checks that the recipient is the party the decision names."""
    arbiter = keypair("arbiter")
    recipient = milestone.contractor if pay_contractor else milestone.investor
    accounts = [AccountMeta(arbiter.pubkey(), True, False), _writable(_key(milestone.address)), _writable(_key(recipient))]
    return await _send("resolve", struct.pack("<?", pay_contractor), accounts, arbiter)


async def claim(milestone: Milestone) -> Tx:
    """Needs no party's signature. The oracle key pays the fee: the contractor's wallet may be empty."""
    accounts = [_writable(_key(milestone.address)), _writable(_key(milestone.contractor))]
    return await _send("claim", b"", accounts, keypair("oracle"))


async def refund(milestone: Milestone) -> Tx:
    investor = keypair("investor")
    accounts = [_writable(investor.pubkey(), signer=True), _writable(_key(milestone.address))]
    return await _send("refund", b"", accounts, investor)


async def read_milestone(address: str) -> Milestone | None:
    """Decode the account; None if it does not exist or is not a Milestone of this program."""
    async with rpc() as client:
        info = (await client.get_account_info(_key(address))).value
    if info is None or info.owner != PROGRAM_ID or bytes(info.data[:8]) != ACCOUNT_DISCRIMINATOR:
        return None
    f = MILESTONE_LAYOUT.unpack_from(info.data, 8)
    return Milestone(
        address=address,
        investor=str(Pubkey(f[0])),
        contractor=str(Pubkey(f[1])),
        oracle=str(Pubkey(f[2])),
        arbiter=str(Pubkey(f[3])),
        amount=f[4],
        ruleset_hash=f[5].hex(),
        deadline=f[6],
        dispute_window=f[7],
        status=STATUSES[f[8]],
        approved_at=f[9],
        disputed_at=f[10],
        asset_hash=f[11].hex(),
        result_hash=f[12].hex(),
        milestone_id=f[13],
    )


async def balances(addresses: dict[str, str]) -> dict[str, int]:
    async with rpc() as client:
        return {name: (await client.get_balance(_key(a))).value for name, a in addresses.items()}


async def chain_time() -> int:
    """Unix time as the program sees it (Clock sysvar), which can differ from wall time."""
    async with rpc() as client:
        data = (await client.get_account_info(CLOCK)).value.data
    return struct.unpack_from("<q", data, 32)[0]  # after slot, epoch_start_timestamp, epoch, leader_schedule_epoch


async def _send(name: str, args: bytes, accounts: list[AccountMeta], signer: Keypair) -> Tx:
    """Send without preflight so even a rejected transaction lands on chain."""
    ix = Instruction(PROGRAM_ID, DISCRIMINATOR[name] + args, accounts)
    async with rpc() as client:
        latest = (await client.get_latest_blockhash()).value
        tx = VersionedTransaction(MessageV0.try_compile(signer.pubkey(), [ix], [], latest.blockhash), [signer])
        signature = (await client.send_transaction(tx, TxOpts(skip_preflight=True))).value
        # A dropped transaction (e.g. the fee payer ran dry) raises once its blockhash expires.
        await client.confirm_transaction(signature, Confirmed, last_valid_block_height=latest.last_valid_block_height)
        result = await client.get_transaction(signature, commitment=Confirmed, max_supported_transaction_version=0)
    meta = result.value.transaction.meta
    return Tx(signature=str(signature), ok=meta.err is None, error=_error_name(meta.err), logs=meta.log_messages or [])


def _error_name(err) -> str | None:
    if err is None:
        return None
    if isinstance(err, TransactionErrorInstructionError) and isinstance(err.err, InstructionErrorCustom):
        return ERROR_NAMES.get(err.err.code, f"Custom({err.err.code})")
    return str(err)


def _writable(pubkey: Pubkey, signer: bool = False) -> AccountMeta:
    return AccountMeta(pubkey, signer, True)


def _key(address: str) -> Pubkey:
    return Pubkey.from_string(address)
