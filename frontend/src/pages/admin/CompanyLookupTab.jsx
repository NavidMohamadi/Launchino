import { useState } from 'react'
import * as api from '../../api'

export default function CompanyLookupTab() {
  const [companyId, setCompanyId] = useState('')
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  async function handleSearch(e) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setReport(null)
    try {
      const result = await api.getCompanyReport(companyId.trim())
      setReport(result)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <h2>Company lookup</h2>
      <form onSubmit={handleSearch} className="search-box">
        <input placeholder="Company ID" value={companyId} onChange={(e) => setCompanyId(e.target.value)} required />
        <button type="submit" disabled={loading}>{loading ? 'Searching...' : 'Search'}</button>
      </form>
      {error && <p className="hint-error">{error}</p>}

      {report && (
        <div>
          <h3 className="category-heading">{report.display_name}</h3>
          <p style={{ fontSize: 13, color: '#666' }}>{report.legal_name} -- <code>{report.company_id}</code></p>

          <div className="stat-grid">
            <div className="stat-box"><div className="stat-value">{report.vacancies_posted}</div><div className="stat-label">Vacancies posted</div></div>
            <div className="stat-box"><div className="stat-value">{report.match_runs}</div><div className="stat-label">Match runs</div></div>
            <div className="stat-box"><div className="stat-value">${report.total_ai_cost_usd.toFixed(6)}</div><div className="stat-label">Total AI cost</div></div>
          </div>

          <h3 className="category-heading">Vacancies</h3>
          <table className="report-table">
            <thead><tr><th>Title</th><th>Status</th></tr></thead>
            <tbody>
              {report.vacancies.map((v) => (
                <tr key={v.vacancy_id}><td>{v.title}</td><td>{v.lifecycle_status}</td></tr>
              ))}
            </tbody>
          </table>

          <h3 className="category-heading">Shortlisted candidates by vacancy ({report.shortlisted_lanes.join(', ')})</h3>
          {report.shortlisted_by_vacancy.length === 0 && <p>None yet.</p>}
          {report.shortlisted_by_vacancy.length > 0 && (
            <table className="report-table">
              <thead><tr><th>Vacancy</th><th>Shortlisted candidates</th></tr></thead>
              <tbody>
                {report.shortlisted_by_vacancy.map((v) => (
                  <tr key={v.vacancy_id}><td>{v.title}</td><td>{v.shortlisted_count}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
