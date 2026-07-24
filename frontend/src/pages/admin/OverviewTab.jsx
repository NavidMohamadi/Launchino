import { useEffect, useState } from 'react'
import * as api from '../../api'
import SignupsChart from './SignupsChart'

function ActiveDormant() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => { api.getCandidateActivity().then(setData).catch((err) => setError(err.message)) }, [])
  if (error) return <p className="hint-error">Could not load candidate activity: {error}</p>
  if (!data) return <p>Loading...</p>
  return (
    <div>
      <h3 className="category-heading">Active vs. dormant candidates (last {data.window_days} days)</h3>
      <div className="stat-grid">
        <div className="stat-box"><div className="stat-value">{data.active_count}</div><div className="stat-label">Active</div></div>
        <div className="stat-box"><div className="stat-value">{data.dormant_count}</div><div className="stat-label">Dormant</div></div>
      </div>
    </div>
  )
}

function SubscriptionBreakdown() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => { api.getSubscriptionBreakdown().then(setData).catch((err) => setError(err.message)) }, [])
  if (error) return <p className="hint-error">Could not load subscriptions: {error}</p>
  if (!data) return <p>Loading...</p>
  const statuses = ['none', 'active', 'expired']
  return (
    <div>
      <h3 className="category-heading">Subscription breakdown</h3>
      <div className="stat-grid">
        {statuses.map((s) => (
          <div key={s} className="stat-box">
            <div className="stat-value">{data.by_status[s] || 0}</div>
            <div className="stat-label">{s}</div>
          </div>
        ))}
        <div className="stat-box">
          <div className="stat-value">
            {data.non_subscriber_campaign_opt_in.rate != null ? `${(data.non_subscriber_campaign_opt_in.rate * 100).toFixed(0)}%` : 'n/a'}
          </div>
          <div className="stat-label">Campaign opt-in (non-subscribers)</div>
        </div>
      </div>
    </div>
  )
}

function IngestionHealth() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => { api.getIngestionHealth().then(setData).catch((err) => setError(err.message)) }, [])
  if (error) return <p className="hint-error">Could not load ingestion health: {error}</p>
  if (!data) return <p>Loading...</p>
  return (
    <div>
      <h3 className="category-heading">Ingestion health</h3>
      <table className="report-table">
        <thead><tr><th>Company</th><th>Source</th><th>Status</th><th>Jobs seen</th><th>Last polled</th></tr></thead>
        <tbody>
          {data.map((row) => {
            const isProblem = row.last_poll_health === 'error' || row.last_poll_health === 'empty'
            return (
              <tr key={row.source_record_id}>
                <td>{row.company_name}</td>
                <td>{row.source_id}</td>
                <td>
                  <span className={isProblem ? 'hint-error' : row.last_poll_health === 'ok' ? 'hint-success' : ''}
                    style={{ padding: '2px 6px', borderRadius: 4 }}>
                    {row.last_poll_health}
                  </span>
                </td>
                <td>{row.last_jobs_seen ?? 'n/a'}</td>
                <td>{row.last_polled_at ? new Date(row.last_polled_at).toLocaleString() : 'never'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default function OverviewTab() {
  return (
    <div className="card">
      <SignupsChart />
      <ActiveDormant />
      <SubscriptionBreakdown />
      <IngestionHealth />
    </div>
  )
}
