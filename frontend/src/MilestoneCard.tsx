import { countdown, sol, type MilestoneView } from './api'
import { ExplorerLink, Hash } from './ui'

const ZERO_HASH = '0'.repeat(64)
const time = (unix: number) => new Date(unix * 1000).toLocaleTimeString()

/** Everything here is read from the milestone account on chain, not from our server. */
export function MilestoneCard({ view }: { view: MilestoneView }) {
  const { milestone: m, balances } = view
  const claimIn = view.window_ends_at === null ? 0 : view.window_ends_at - view.now + 1 // claim needs now > end
  return (
    <section className="card">
      <div className="card-head">
        <span className={`status status-${m.status.toLowerCase()}`}>{m.status}</span>
        <span className="amount">{sol(m.amount)} SOL</span>
      </div>

      <dl className="facts">
        <dt>Escrow account</dt>
        <dd>
          <Hash value={m.address} /> holds {sol(balances.milestone)} SOL <ExplorerLink path={`address/${m.address}`} />
        </dd>
        <dt>Frozen ruleset</dt>
        <dd>
          {view.ruleset_name ?? 'unknown'} <Hash value={m.ruleset_hash} />
        </dd>
        <dt>Deadline</dt>
        <dd>
          {time(m.deadline)}
          {m.status === 'Open' && ` (${countdown(m.deadline - view.now)})`}
        </dd>
        <dt>Dispute window</dt>
        <dd>{m.dispute_window} s after approval</dd>
        {view.window_ends_at !== null && (
          <>
            <dt>{m.status === 'Approved' ? 'Investor may dispute' : 'Arbiter may decide'}</dt>
            <dd>
              until {time(view.window_ends_at)} — {m.status === 'Disputed' && 'if undecided, '}
              {claimIn > 0 ? `claimable ${countdown(claimIn)}` : 'claimable now'}
            </dd>
          </>
        )}
        {m.asset_hash !== ZERO_HASH && (
          <>
            <dt>Accepted IFC</dt>
            <dd>
              <Hash value={m.asset_hash} />
            </dd>
            <dt>Accepted QA result</dt>
            <dd>
              <Hash value={m.result_hash} />
            </dd>
          </>
        )}
      </dl>

      <div className="parties">
        <Party role="Investor" address={m.investor} lamports={balances.investor} />
        <Party role="Contractor" address={m.contractor} lamports={balances.contractor} />
        <Party role="Oracle" address={m.oracle} />
        <Party role="Arbiter" address={m.arbiter} />
      </div>
    </section>
  )
}

function Party({ role, address, lamports }: { role: string; address: string; lamports?: number }) {
  return (
    <div className="party">
      <span className="party-role">{role}</span>
      <Hash value={address} />
      {lamports !== undefined && <span className="party-balance">{sol(lamports)} SOL</span>}
    </div>
  )
}
