"""Environment-dependent settings. Defaults match scripts/localnet.sh; CLUSTER=devnet switches to devnet."""

import os
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]

CLUSTER = os.getenv("CLUSTER", "localnet")
DEFAULT_RPC = {"localnet": "http://127.0.0.1:8899", "devnet": "https://api.devnet.solana.com"}
if CLUSTER not in DEFAULT_RPC:
    raise SystemExit(f"CLUSTER must be localnet or devnet, got {CLUSTER!r}")
RPC_URL = os.getenv("RPC_URL", DEFAULT_RPC[CLUSTER])
# Query string that makes Solana Explorer show transactions of this cluster.
EXPLORER_QUERY = "cluster=devnet" if CLUSTER == "devnet" else "cluster=custom&customUrl=" + quote(RPC_URL, safe="")

RULES_DIR = Path(os.getenv("RULES_DIR", ROOT / "rules"))
KEYS_DIR = Path(os.getenv("KEYS_DIR", ROOT / ".keys"))
# The IDL carries the program id, instruction discriminators and error names,
# so the backend can never disagree with the deployed program about them.
IDL_PATH = Path(os.getenv("IDL_PATH", ROOT / "program/target/idl/milestone_escrow.json"))

# Fee payers below this get a warning in the UI (/api/health). 0.01 SOL pays ~2000 transaction fees.
LOW_BALANCE = 10_000_000
