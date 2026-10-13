import { useState } from 'react'
import { api, sol, type ActionResponse, type MilestoneView } from './api'
import { MilestoneCard } from './MilestoneCard'
import { useAction } from './useAction'
import { Hash, Notice, Tip, TxResult } from './ui'

type Outcome = { title: string; txLabel: string; response: ActionResponse; paid: number }

export function ContractorView({ view, onView }: { view: MilestoneView | null; onView: (v: MilestoneView) => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const { busy, error, run } = useAction(onView)

  if (!view) return <Notice text="No milestone yet. Create one in the Investor view." />
  const address = view.milestone.address
  const status = view.milestone.status
  const approved = status === 'Approved' || status === 'Disputed'
  // What happened last decides the next hint.
  const last = outcome?.response
  const failed = last?.qa?.result.passed === false
  const lastError = last?.tx?.error

  async function act(title: string, txLabel: string, action: () => Promise<ActionResponse>) {
    const before = view!.balances.contractor
    const response = await run(action)
    if (response) setOutcome({ title, txLabel, response, paid: response.view.balances.contractor - before })
  }

  return (
    <>
      <MilestoneCard view={view} />

      <section className="panel">
        <h2>Deliver the model</h2>
        <Tip when={status === 'Open' && !last}>
          3. Choose <code>demo/architecture_broken.ifc</code> and click Submit for QA. This model is missing some data,
          so it should fail.
        </Tip>
        <Tip when={status === 'Open' && failed}>
          4. Now try to cheat: click "Get paid with the lenient ruleset" below. The easier rules let this model pass,
          but the program knows which rules were agreed and will refuse.
        </Tip>
        <Tip when={status === 'Open' && lastError === 'RulesetMismatch'}>
          5. Refused, as expected. Now choose <code>demo/architecture_valid.ifc</code> and click Submit for QA.
        </Tip>
        <Tip when={status === 'Approved' && lastError !== 'ClaimTooEarly'}>
          6. Approved, but no money has moved yet. Click Claim payment right away: the program will refuse, because
          the investor can still dispute.
        </Tip>
        <Tip when={status === 'Approved' && lastError === 'ClaimTooEarly'}>
          7. Wait until the card says "claimable now", then click Claim payment again.
        </Tip>
        <Tip when={status === 'Released' && lastError !== 'NotApproved'}>
          8. Paid. Click "Claim payment again" below to check that the program won't pay twice.
        </Tip>
        <Tip when={status === 'Released' && lastError === 'NotApproved'}>
          That's the main story. For a dispute or a refund, go back to the Investor tab.
        </Tip>
        <Tip when={status === 'Disputed'}>The investor disputed. Open the Arbiter tab to decide.</Tip>
        <div className="actions">
          <input type="file" accept=".ifc" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <button
            className="primary"
            disabled={busy || !file}
            onClick={() => act('QA against the frozen rules', 'Approved on chain', () => api.submit(address, file!))}
          >
            Submit for QA
          </button>
        </div>
        <div className="actions">
          <button className="primary" disabled={busy || !approved} onClick={() => act('Claim', 'Paid', () => api.claim(address))}>
            Claim payment
          </button>
          <span className="hint">
            After a PASS the oracle approves; the payment is claimable once the dispute window has passed.
          </span>
        </div>
      </section>

      {error && <Notice kind="error" text={error} />}
      {outcome && <OutcomePanel {...outcome} />}

      <section className="panel attacks">
        <h2>Demo attacks</h2>
        <div className="attack">
          <button
            disabled={busy || !file}
            onClick={() => act('Attack: easier rules', 'Approved', () => api.attackLenient(address, file!))}
          >
            Get paid with the lenient ruleset
          </button>
          <span className="hint">QA runs with rules the investor never agreed to, then the oracle asks for approval.</span>
        </div>
        <div className="attack">
          <button disabled={busy} onClick={() => act('Attack: pay twice', 'Paid', () => api.claim(address))}>
            Claim payment again
          </button>
          <span className="hint">Sends another claim after the milestone was already settled.</span>
        </div>
      </section>
    </>
  )
}

function OutcomePanel({ title, txLabel, response, paid }: Outcome) {
  const { qa, tx, note } = response
  const frozen = response.view.milestone.ruleset_hash
  // A PASS under rules other than the frozen ones is not a success: say so before the program rejects it.
  const foreign = qa !== null && qa.result.ruleset_hash !== frozen
  return (
    <section className="panel outcome">
      <h2>{title}</h2>
      {qa && (
        <>
          <div className={`verdict ${foreign ? 'foreign' : qa.result.passed ? 'pass' : 'fail'}`}>
            {qa.result.passed ? 'PASS' : 'FAIL'}
            {foreign && ' — under rules NOT agreed for this milestone'}
            <small>{qa.ruleset_name}</small>
          </div>
          {foreign && (
            <p className="mismatch">
              Frozen on chain <Hash value={frozen} /> ≠ used by QA <Hash value={qa.result.ruleset_hash} />
            </p>
          )}
          {qa.result.violations.length > 0 && (
            <ul className="violations">
              {qa.result.violations.map((v) => (
                <li key={v.rule + v.global_id}>
                  <strong>{v.element}</strong> — {v.rule.toLowerCase()}: {v.reason}
                </li>
              ))}
            </ul>
          )}
          <p className="hashes">
            IFC <Hash value={qa.result.asset_hash} /> rules <Hash value={qa.result.ruleset_hash} /> result{' '}
            <Hash value={qa.result_hash} />
          </p>
        </>
      )}
      {tx && <TxResult label={txLabel} tx={tx} />}
      {note && <Notice text={note} />}
      {paid > 0 && <p className="paid">Contractor received +{sol(paid)} SOL</p>}
    </section>
  )
}
