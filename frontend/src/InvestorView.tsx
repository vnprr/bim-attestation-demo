import { useEffect, useState } from 'react'
import { api, type ActionResponse, type MilestoneView, type Ruleset, type Tx } from './api'
import { MilestoneCard } from './MilestoneCard'
import { useAction } from './useAction'
import { Hash, Notice, Tip, TxResult } from './ui'

const DEADLINES = [
  { label: '5 min', seconds: 300 },
  { label: '30 s (refund demo)', seconds: 30 },
]
const WINDOWS = [
  { label: '20 s (demo)', seconds: 20 },
  { label: '1 h', seconds: 3600 },
]

type Props = {
  view: MilestoneView | null
  onCreated: (view: MilestoneView) => void
  onView: (view: MilestoneView) => void
}

export function InvestorView({ view, onCreated, onView }: Props) {
  const [rulesets, setRulesets] = useState<Ruleset[]>([])
  const [rulesetHash, setRulesetHash] = useState('')
  const [amount, setAmount] = useState(1)
  const [deadline, setDeadline] = useState(DEADLINES[0].seconds)
  const [disputeWindow, setDisputeWindow] = useState(WINDOWS[0].seconds)
  const [last, setLast] = useState<{ label: string; tx: Tx; address: string } | null>(null)
  const { busy, error, run } = useAction(onView)

  useEffect(() => {
    api.rulesets().then((list) => {
      setRulesets(list)
      setRulesetHash((list.find((r) => r.name.endsWith('Strict')) ?? list[0])?.hash ?? '')
    })
  }, [])

  async function lockFunds() {
    const response = await run(() => api.create(amount, deadline, disputeWindow, rulesetHash))
    if (response?.tx) {
      onCreated(response.view)
      setLast({ label: 'Funds locked', tx: response.tx, address: response.view.milestone.address })
    }
  }

  async function send(label: string, action: (address: string) => Promise<ActionResponse>) {
    const response = await run(() => action(view!.milestone.address))
    if (response?.tx) setLast({ label, tx: response.tx, address: response.view.milestone.address })
  }

  const status = view?.milestone.status
  const refundable = status === 'Open' && view!.now > view!.milestone.deadline
  const disputable = status === 'Approved' && view!.now <= view!.window_ends_at!

  return (
    <>
      <section className="panel">
        <h2>New milestone</h2>
        <Tip when={!view}>
          1. Leave the defaults and click Lock funds. 1 SOL leaves the investor's wallet and is held by the program
          from now on, not by the investor and not by us.
        </Tip>
        <div className="form">
          <label>
            Amount (SOL)
            <input type="number" min={0.1} step={0.1} value={amount} onChange={(e) => setAmount(+e.target.value)} />
          </label>
          <Choices id="deadline" label="Deadline" options={DEADLINES} value={deadline} onChange={setDeadline} />
          <Choices id="window" label="Dispute window" options={WINDOWS} value={disputeWindow} onChange={setDisputeWindow} />
          <label>
            Acceptance rules (IDS)
            <select value={rulesetHash} onChange={(e) => setRulesetHash(e.target.value)}>
              {rulesets.map((r) => (
                <option key={r.hash} value={r.hash}>
                  {r.name}
                </option>
              ))}
            </select>
          </label>
          {rulesetHash && (
            <p className="hint">
              Fingerprint frozen on chain: <Hash value={rulesetHash} />
            </p>
          )}
          <button className="primary" disabled={busy || !rulesetHash || amount <= 0} onClick={lockFunds}>
            Lock funds
          </button>
        </div>
      </section>

      {error && <Notice kind="error" text={error} />}
      {last && last.address === view?.milestone.address && <TxResult label={last.label} tx={last.tx} />}

      {view && (
        <>
          <MilestoneCard view={view} />
          <Tip when={status === 'Open' && !refundable}>
            2. The money is locked and the rules are frozen: the card shows their fingerprint. Now open the Contractor
            tab.
          </Tip>
          <Tip when={refundable}>The deadline has passed and nothing was approved. Click Refund to get the money back.</Tip>
          <Tip when={disputable}>
            Not happy with the approved model? Click Dispute before the window closes and the arbiter will decide. If
            you do nothing, the contractor gets paid.
          </Tip>
          <Tip when={status === 'Disputed'}>Disputed. Now open the Arbiter tab: the arbiter decides who gets the money.</Tip>
          <Tip when={status === 'Released' || status === 'Refunded'}>
            This one is settled. To show a dispute: lock funds again, deliver the valid model, and click Dispute here
            while the window is open. To show a refund: pick the 30 s deadline, deliver nothing, and click Refund once
            the deadline has passed.
          </Tip>
          <div className="actions">
            <button disabled={busy || !disputable} onClick={() => send('Disputed', api.dispute)}>
              Dispute
            </button>
            <span className="hint">
              While the window is open after an approval. Then the arbiter decides; if it stays silent, the approval stands.
            </span>
          </div>
          <div className="actions">
            <button disabled={busy || !refundable} onClick={() => send('Refunded', api.refund)}>
              Refund
            </button>
            <span className="hint">
              {status === 'Open'
                ? 'Possible only after the deadline, if the oracle has not approved a delivery.'
                : 'Only an open milestone can be refunded after its deadline.'}
            </span>
          </div>
        </>
      )}
    </>
  )
}

type ChoicesProps = {
  id: string
  label: string
  options: { label: string; seconds: number }[]
  value: number
  onChange: (seconds: number) => void
}

function Choices({ id, label, options, value, onChange }: ChoicesProps) {
  return (
    <div className="field" role="group" aria-labelledby={`${id}-label`}>
      <span id={`${id}-label`}>{label}</span>
      <span className="choices">
        {options.map((o) => (
          <button key={o.seconds} className={o.seconds === value ? 'chosen' : ''} onClick={() => onChange(o.seconds)}>
            {o.label}
          </button>
        ))}
      </span>
    </div>
  )
}
