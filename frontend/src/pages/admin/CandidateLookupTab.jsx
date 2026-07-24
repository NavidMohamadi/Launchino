import { useState } from 'react'
import * as api from '../../api'

export default function CandidateLookupTab() {
  const [talentId, setTalentId] = useState('')
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  async function handleSearch(e) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setReport(null)
    try {
      const result = await api.getCandidateReport(talentId.trim())
      setReport(result)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <h2>Candidate lookup</h2>
      <form onSubmit={handleSearch} className="search-box">
        <input placeholder="Candidate (talent) ID" value={talentId} onChange={(e) => setTalentId(e.target.value)} required />
        <button type="submit" disabled={loading}>{loading ? 'Searching...' : 'Search'}</button>
      </form>
      {error && <p className="hint-error">{error}</p>}

      {report && (
        <div>
          <h3 className="category-heading">{report.full_name}</h3>
          <p style={{ fontSize: 13, color: '#666' }}>{report.email} -- <code>{report.talent_id}</code></p>

          <div className="stat-grid">
            <div className="stat-box">
              <div className="stat-value">{report.profile_completeness.coverage_percent}%</div>
              <div className="stat-label">Profile coverage</div>
            </div>
            <div className="stat-box">
              <div className="stat-value">
                {report.profile_completeness.elements_answered}/{report.profile_completeness.elements_active_for_candidate}
              </div>
              <div className="stat-label">Elements answered</div>
            </div>
            <div className="stat-box">
              <div className="stat-value">${report.total_ai_cost_usd.toFixed(6)}</div>
              <div className="stat-label">Total AI cost</div>
            </div>
            <div className="stat-box">
              <div className="stat-value">{report.recommendations.length}</div>
              <div className="stat-label">Recommendations</div>
            </div>
          </div>

          <h3 className="category-heading">Job-discovery recommendations</h3>
          {report.recommendations.length === 0 && <p>None yet.</p>}
          {report.recommendations.length > 0 && (
            <table className="report-table">
              <thead><tr><th>Vacancy</th><th>Lane</th><th>Score</th><th>Coverage</th><th>Generated</th></tr></thead>
              <tbody>
                {report.recommendations.map((r) => (
                  <tr key={r.recommendation_id}>
                    <td><code>{r.vacancy_id}</code></td>
                    <td>{r.result_lane}</td>
                    <td>{r.overall_score != null ? `${r.overall_score.toFixed(1)}%` : 'n/a'}</td>
                    <td>{r.overall_coverage.toFixed(1)}%</td>
                    <td>{new Date(r.generated_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
