#!/usr/bin/env bash
# Local Solana validator with the escrow program preloaded and the demo keys funded.
# Usage: scripts/localnet.sh        (Ctrl-C stops the validator; every start is a fresh chain)
set -euo pipefail
cd "$(dirname "$0")/.."

PROGRAM_SO=program/target/deploy/milestone_escrow.so
IDL=program/target/idl/milestone_escrow.json
URL=http://127.0.0.1:8899

[[ -f $PROGRAM_SO && -f $IDL ]] || { echo "Program not built. Run: cd program && anchor build" >&2; exit 1; }
# Load the program at the id it was built with (declare_id!, copied into the IDL), so the
# local chain, the program and the backend always agree, whatever keypair is in target/deploy.
PROGRAM_ID=$(grep -m1 '"address"' $IDL | cut -d'"' -f4)

# Demo keypairs. Gitignored, created once.
mkdir -p .keys
for role in investor contractor oracle arbiter; do
  [[ -f .keys/$role.json ]] || solana-keygen new --no-bip39-passphrase --silent --outfile ".keys/$role.json"
done

solana-test-validator --reset --quiet --ledger test-ledger \
  --bpf-program "$PROGRAM_ID" "$PROGRAM_SO" &
VALIDATOR=$!
trap 'kill $VALIDATOR' EXIT INT TERM

until solana cluster-version --url $URL >/dev/null 2>&1; do sleep 1; done

# The contractor starts at 0 SOL so the payout is easy to see.
solana airdrop 100 .keys/investor.json --url $URL >/dev/null
solana airdrop 10 .keys/oracle.json --url $URL >/dev/null
solana airdrop 1 .keys/arbiter.json --url $URL >/dev/null

echo "Validator ready at $URL, program $PROGRAM_ID"
for role in investor contractor oracle arbiter; do
  printf '  %-10s %s\n' "$role" "$(solana address -k .keys/$role.json)"
done
wait $VALIDATOR
