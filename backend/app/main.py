"""QA-gated milestone escrow API.   uv run uvicorn app.main:app --port 8080"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from solana.exceptions import SolanaRpcException
from solana.rpc.core import TransactionExpiredBlockheightExceededError, UnconfirmedTxError

from .config import CLUSTER, RPC_URL
from .routes import router

app = FastAPI(title="QA-gated milestone escrow")
app.include_router(router)


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": message})


@app.exception_handler(LookupError)
async def not_found(_: Request, error: LookupError) -> JSONResponse:
    return _error(404, str(error))


@app.exception_handler(ValueError)
async def bad_request(_: Request, error: ValueError) -> JSONResponse:
    return _error(400, str(error))


@app.exception_handler(SolanaRpcException)
async def rpc_unreachable(_: Request, error: SolanaRpcException) -> JSONResponse:
    hint = "Is scripts/localnet.sh running?" if CLUSTER == "localnet" else "Devnet may be down or rate-limiting."
    return _error(503, f"Solana RPC not reachable at {RPC_URL}. {hint}")


@app.exception_handler(UnconfirmedTxError)
@app.exception_handler(TransactionExpiredBlockheightExceededError)
async def tx_dropped(_: Request, error: Exception) -> JSONResponse:
    return _error(504, "Transaction was not confirmed and has expired. Most likely the fee payer has no SOL: check /api/health.")
