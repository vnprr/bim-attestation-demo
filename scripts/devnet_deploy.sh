#!/usr/bin/env bash
# Deploy (or upgrade) the escrow program on devnet and fund the demo keys from a deployer wallet.
# Usage: scripts/devnet_deploy.sh      then: cd backend && CLUSTER=devnet uv run uvicorn app.main:app --port 8080
# Fund the deployer beforehand at https://faucet.solana.com. Never rely on an airdrop during the demo.
set -euo pipefail
cd "$(dirname "$0")/.."

URL=${RPC_URL:-https://api.devnet.solana.com}
DEPLOYER=.keys/deployer.json
PROGRAM_SO=program/target/deploy/milestone_escrow.so
PROGRAM_KEY=program/target/deploy/milestone_escrow-keypair.json
# role:lamports each demo key is topped up to (the contractor starts empty, so the payout is easy to see)
TARGETS="investor:2500000000 oracle:100000000 arbiter:50000000"

# Deployer and demo keypairs. Gitignored, created once.
mkdir -p .keys
for role in deployer investor contractor oracle arbiter; do
  [[ -f .keys/$role.json ]] || solana-keygen new --no-bip39-passphrase --silent --outfile ".keys/$role.json"
done
lamports() { solana balance "$1" --url "$URL" --lamports | cut -d' ' -f1; }

# 1. Build. `keys sync` writes the id of YOUR program keypair into the code: each deployer owns their copy.
(cd program && anchor keys sync && anchor build)
PROGRAM_ID=$(solana address -k $PROGRAM_KEY)

# 2. Enough SOL? A deploy needs rent for ~2x the program size (upload buffer + program), plus the top-ups.
need=$(solana rent $(( 2 * $(wc -c < $PROGRAM_SO) )) --lamports | grep -o '[0-9]*' | head -1)
for t in $TARGETS; do need=$(( need + ${t#*:} )); done
have=$(lamports $DEPLOYER)
if (( have < need )); then
  echo "Deployer $(solana address -k $DEPLOYER) has $have lamports, needs ~$need." >&2
  echo "Fund it at https://faucet.solana.com (devnet), then run this script again." >&2
  exit 1
fi

# 3. Deploy, or upgrade in place if it is already deployed. The deployer is the upgrade authority.
# --use-rpc: send through the RPC URL only (no direct TPU/websocket connections, which some proxies break).
solana program deploy $PROGRAM_SO --program-id $PROGRAM_KEY --keypair $DEPLOYER \
  --upgrade-authority $DEPLOYER --url "$URL" --use-rpc

# 4. Top up the demo keys with plain transfers from the deployer.
for t in $TARGETS; do
  role=${t%%:*} target=${t#*:} current=$(lamports .keys/$role.json)
  if (( current < target )); then
    sol=$(awk "BEGIN { printf \"%.9f\", ($target - $current) / 1e9 }")
    solana transfer "$(solana address -k .keys/$role.json)" "$sol" --keypair $DEPLOYER --allow-unfunded-recipient --url "$URL" >/dev/null
  fi
done

echo "Program $PROGRAM_ID on devnet: https://explorer.solana.com/address/$PROGRAM_ID?cluster=devnet"
for role in investor contractor oracle arbiter; do
  printf '  %-10s %s  %s lamports\n' "$role" "$(solana address -k .keys/$role.json)" "$(lamports .keys/$role.json)"
done
echo "Upgrade authority: $(solana address -k $DEPLOYER) (.keys/deployer.json). To make the program immutable (irreversible):"
echo "  solana program set-upgrade-authority $PROGRAM_ID --final --keypair $DEPLOYER --url $URL"
