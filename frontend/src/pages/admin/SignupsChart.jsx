import { useEffect, useState } from 'react'
import * as api from '../../api'

const GRANULARITIES = ['day', 'week', 'month']

function formatPeriod(iso, granularity) {
  const d = new Date(iso)
  if (granularity === 'month') return d.toLocaleDateString(undefined, { month: 'short', year: '2-digit' })
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export default function SignupsChart() {
  const [granularity, setGranularity] = useState('day')
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    setData(null)
    api.getSignups(granularity).then(setData).catch((err) => setError(err.message))
  }, [granularity])

  if (error) return <p className="hint-error">Could not load signups: {error}</p>
  if (!data) return <p>Loading signups...</p>

  const periods = [...new Set([...data.candidates.map((r) => r.period), ...data.companies.map((r) => r.period)])].sort()
  const candidateByPeriod = Object.fromEntries(data.candidates.map((r) => [r.period, r.count]))
  const companyByPeriod = Object.fromEntries(data.companies.map((r) => [r.period, r.count]))
  const maxCount = Math.max(1, ...periods.map((p) => Math.max(candidateByPeriod[p] || 0, companyByPeriod[p] || 0)))

  return (
    <div>
      <h3 className="category-heading">Signups over time</h3>
      <div className="tri-state-toggle">
        {GRANULARITIES.map((g) => (
          <label key={g} className={granularity === g ? 'active' : ''}>
            <input type="radio" checked={granularity === g} onChange={() => setGranularity(g)} />
            {g}
          </label>
        ))}
      </div>
      <div className="bar-chart-legend">
        <span><span className="swatch" style={{ background: '#2d2d86' }} /> Candidates</span>
        <span><span className="swatch" style={{ background: '#8a8ad8' }} /> Companies</span>
      </div>
      {periods.length === 0 && <p>No signups recorded yet.</p>}
      <div className="bar-chart">
        {periods.map((period) => {
          const cCount = candidateByPeriod[period] || 0
          const coCount = companyByPeriod[period] || 0
          return (
            <div key={period} className="bar-col">
              <div className="bar-pair">
                <div className="bar candidates" style={{ height: `${(cCount / maxCount) * 100}%` }} title={`${cCount} candidates`} />
                <div className="bar companies" style={{ height: `${(coCount / maxCount) * 100}%` }} title={`${coCount} companies`} />
              </div>
              <span className="bar-label">{formatPeriod(period, granularity)}</span>
            </div>
          )
        })}
      </div>
      <table className="report-table">
        <thead><tr><th>Period</th><th>Candidates</th><th>Companies</th></tr></thead>
        <tbody>
          {periods.map((period) => (
            <tr key={period}>
              <td>{formatPeriod(period, granularity)}</td>
              <td>{candidateByPeriod[period] || 0}</td>
              <td>{companyByPeriod[period] || 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
