import { useEffect, useState } from 'react'
import { api, short, type Health, type MilestoneView } from './api'
import { ArbiterView } from './ArbiterView'
import { ContractorView } from './ContractorView'
import { GuideOn, useGuideToggle } from './guide'
import { InvestorView } from './InvestorView'
import { Notice, Tip } from './ui'

type Tab = 'investor' | 'contractor' | 'arbiter'
const TABS: Record<Tab, string> = { investor: 'Investor', contractor: 'Contractor', arbiter: 'Arbiter' }
const POLL_MS = 2000
const HEALTH_MS = 15000

export default function App() {
  const [tab, setTab] = useState<Tab>('investor')
  const [addresses, setAddresses] = useState<string[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [view, setView] = useState<MilestoneView | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [down, setDown] = useState<string | null>(null)
  const guide = useGuideToggle()

  // On devnet a fee payer can run dry mid-demo: warn early instead of failing a transaction.
  useEffect(() => {
    const load = () =>
      api.health().then(
        (h) => {
          setHealth(h)
          setDown(null)
        },
        (e: Error) => setDown(e.message),
      )
    load()
    const timer = setInterval(load, HEALTH_MS)
    return () => clearInterval(timer)
  }, [])

  // Milestone state always comes from the chain; poll it so countdowns and balances stay live.
  useEffect(() => {
    if (!selected) return
    let active = true
    const load = () => api.milestone(selected).then((v) => active && setView(v), () => {})
    const timer = setInterval(load, POLL_MS)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [selected])

  function onCreated(created: MilestoneView) {
    setAddresses((list) => [...list, created.milestone.address])
    select(created.milestone.address, created)
  }

  function select(address: string, initial: MilestoneView | null = null) {
    setSelected(address)
    setView(initial)
    if (!initial) api.milestone(address).then(setView, () => {})
  }

  const current = view?.milestone.address === selected ? view : null

  return (
    <GuideOn.Provider value={guide.on}>
      <main>
        <header>
          <h1>
            QA-Gated Milestone Escrow {health && <span className="cluster">{health.cluster}</span>}
            <button className="guide-toggle" onClick={guide.toggle}>
              Guide: {guide.on ? 'on' : 'off'}
            </button>
          </h1>
          <p>A Solana program holds the payment for a BIM model and pays it only if the model passes the acceptance rules frozen before work started, after a short dispute window.</p>
        </header>

        <Tip when={addresses.length === 0}>
          Welcome. This demo shows a payment for a building model that sits in a Solana program and is paid out only
          if the model passes the rules both sides agreed on before work started. Follow the numbered hints, it takes
          about three minutes. Turn them off with the Guide button above.
        </Tip>

        {down && <Notice kind="error" text={down} />}
        {health && health.low.length > 0 && (
          <Notice kind="error" text={`Low SOL on ${health.cluster}: ${health.low.join(', ')}. Fund these keys before the next transaction.`} />
        )}

        <nav>
          <div className="tabs">
            {(Object.keys(TABS) as Tab[]).map((t) => (
              <button key={t} className={t === tab ? 'active' : ''} onClick={() => setTab(t)}>
                {TABS[t]}
              </button>
            ))}
          </div>
          {addresses.length > 0 && (
            <div className="milestones">
              <span className="hint">Milestones:</span>
              {addresses.map((a, i) => (
                <button key={a} className={a === selected ? 'chosen' : ''} onClick={() => select(a)}>
                  #{i + 1} <code>{short(a)}</code>
                </button>
              ))}
            </div>
          )}
        </nav>

        {tab === 'investor' && <InvestorView view={current} onCreated={onCreated} onView={setView} />}
        {tab === 'contractor' && <ContractorView key={selected} view={current} onView={setView} />}
        {tab === 'arbiter' && <ArbiterView key={selected} view={current} onView={setView} />}
      </main>
    </GuideOn.Provider>
  )
}
