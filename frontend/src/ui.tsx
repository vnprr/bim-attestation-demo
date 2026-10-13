import { useContext, useEffect, useState, type ReactNode } from 'react'
import { api, short, type Tx } from './api'
import { GuideOn } from './guide'

const config = api.config() // once per page load: which cluster the backend talks to

/** Opens a transaction (`tx/<sig>`) or account (`address/<key>`) in Solana Explorer on the backend's cluster. */
export function ExplorerLink({ path }: { path: string }) {
  const [query, setQuery] = useState<string | null>(null)
  useEffect(() => {
    config.then((c) => setQuery(c.explorer_query), () => {})
  }, [])
  if (!query) return null
  return (
    <a href={`https://explorer.solana.com/${path}?${query}`} target="_blank" rel="noreferrer">
      explorer ↗
    </a>
  )
}

/** Shortened hash or address; click copies the full value. */
export function Hash({ value }: { value: string }) {
  return (
    <button className="hash" title={`${value}\n(click to copy)`} onClick={() => navigator.clipboard.writeText(value)}>
      {short(value)}
    </button>
  )
}

/** Outcome of one transaction. Rejected ones are real failed transactions on chain. */
export function TxResult({ tx, label }: { tx: Tx; label: string }) {
  return (
    <div className={`tx ${tx.ok ? 'tx-ok' : 'tx-rejected'}`}>
      <div className="tx-head">
        <strong>{tx.ok ? `${label} ✓` : 'TRANSACTION REJECTED'}</strong>
        {tx.error && <code className="tx-error">{tx.error}</code>}
      </div>
      <div className="tx-sig">
        signature <Hash value={tx.signature} />
        <ExplorerLink path={`tx/${tx.signature}`} />
      </div>
      {!tx.ok && (
        <details>
          <summary>program logs</summary>
          <pre>{tx.logs.join('\n')}</pre>
        </details>
      )}
    </div>
  )
}

export function Notice({ text, kind = 'info' }: { text: string; kind?: 'info' | 'error' }) {
  return <p className={`notice notice-${kind}`}>{text}</p>
}

/** One hint for whoever is clicking through the demo. Shown only while the guide is on. */
export function Tip({ when = true, children }: { when?: boolean; children: ReactNode }) {
  const on = useContext(GuideOn)
  if (!on || !when) return null
  return <p className="tip">{children}</p>
}
