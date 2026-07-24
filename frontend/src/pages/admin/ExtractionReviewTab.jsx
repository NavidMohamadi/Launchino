import { useEffect, useState } from 'react'
import * as api from '../../api'

export default function ExtractionReviewTab() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getExtractionReview(50).then(setData).catch((err) => setError(err.message))
  }, [])

  if (error) return <p className="hint-error">Could not load extraction review: {error}</p>
  if (!data) return <p>Loading...</p>

  return (
    <div>
      <h2>Extraction spot-check (read-only)</h2>
      <div className="unmapped-terms">{data.note}</div>

      <h3 className="category-heading">Candidate submissions ({data.candidate_submissions.length})</h3>
      <table className="report-table">
        <thead>
          <tr><th>Candidate</th><th>Element</th><th>Value</th><th>Status</th><th>Submitted</th></tr>
        </thead>
        <tbody>
          {data.candidate_submissions.map((s, i) => (
            <tr key={i}>
              <td>{s.full_name}</td>
              <td><code>{s.element_id}</code></td>
              <td><code style={{ fontSize: 11 }}>{JSON.stringify(s.value)}</code></td>
              <td>{s.value_status}</td>
              <td>{new Date(s.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 className="category-heading">Vacancy submissions ({data.vacancy_submissions.length})</h3>
      <table className="report-table">
        <thead>
          <tr><th>Vacancy</th><th>Company</th><th>Element</th><th>Value</th><th>Status</th><th>Submitted</th></tr>
        </thead>
        <tbody>
          {data.vacancy_submissions.map((s, i) => (
            <tr key={i}>
              <td>{s.title}</td>
              <td>{s.company_name}</td>
              <td><code>{s.element_id}</code></td>
              <td><code style={{ fontSize: 11 }}>{JSON.stringify(s.value)}</code></td>
              <td>{s.value_status}</td>
              <td>{new Date(s.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
