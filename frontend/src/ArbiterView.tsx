import { useState } from 'react'
import { api, type MilestoneView, type Tx } from './api'
import { MilestoneCard } from './MilestoneCard'
import { useAction } from './useAction'
import { Notice, Tip, TxResult } from './ui'

/** The arbiter can only choose between the two parties stored on chain, and only while a dispute is open. */
export function ArbiterView({ view, onView }: { view: MilestoneView | null; onView: (v: MilestoneView) => void }) {
  const [last, setLast] = useState<{ label: string; tx: Tx } | null>(null)
  const { busy, error, run } = useAction(onView)

  if (!view) return <Notice text="No milestone yet. Create one in the Investor view." />
  const m = view.milestone
  const open = m.status === 'Disputed' && view.now <= view.window_ends_at!

  async function decide(payContractor: boolean) {
    const response = await run(() => api.resolve(m.address, payContractor))
    if (response?.tx) setLast({ label: payContractor ? 'Contractor paid' : 'Investor refunded', tx: response.tx })
  }

  return (
    <>
      <MilestoneCard view={view} />

      <section className="panel">
        <h2>Decide the dispute</h2>
        <Tip when={m.status === 'Open' || m.status === 'Approved'}>
          The arbiter only steps in when the investor disputes an approval. Nothing to do here yet.
        </Tip>
        <Tip when={open}>
          Run the command below on the delivered file. If it prints the same three hashes, the oracle told the truth.
          Then pick who gets the money. If you don't decide in time, the contractor gets paid.
        </Tip>
        {m.status !== 'Disputed' ? (
          <p className="hint">Nothing to decide: the arbiter acts only on a disputed milestone (now {m.status}).</p>
        ) : (
          <>
            <p>
              The investor disputes the oracle's PASS. QA is deterministic, so re-running it on the delivered file with
              the frozen rules must print exactly the hashes stored on chain:
            </p>
            <pre className="command">
              {`cd backend
uv run python -m app.reproduce <delivered file>.ifc ../rules/${view.ruleset_file ?? '<ruleset>.ids'}
# expected last lines:
asset_hash   ${m.asset_hash}
ruleset_hash ${m.ruleset_hash}
result_hash  ${m.result_hash}`}
            </pre>
            <div className="actions">
              <button className="primary" disabled={busy || !open} onClick={() => decide(true)}>
                Pay contractor
              </button>
              <button disabled={busy || !open} onClick={() => decide(false)}>
                Refund investor
              </button>
            </div>
            <p className="hint">
              {open
                ? 'If you do not decide in time, the oracle’s approval stands and anyone can claim the payment for the contractor.'
                : 'Your time to decide is over: the oracle’s approval stands.'}
            </p>
          </>
        )}
      </section>

      {error && <Notice kind="error" text={error} />}
      {last && <TxResult label={last.label} tx={last.tx} />}
    </>
  )
}
