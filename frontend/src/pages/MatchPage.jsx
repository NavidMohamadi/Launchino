import { useState } from 'react'
import * as api from '../api'

const DEFAULT_CATEGORY_WEIGHTS = { PRACT: 15.0, CAP: 30.0, TASK: 25.0, TEAM: 10.0, CAREER: 5.0, MOT: 5.0, ENV: 10.0 }

export default function MatchPage() {
  const [vacancyId, setVacancyId] = useState('')
  const [talentId, setTalentId] = useState('')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  async function handleRun(e) {
    e.preventDefault()
    setRunning(true)
    setError(null)
    setResult(null)
    try {
      const res = await api.runMatch(vacancyId, {
        talent_ids: [talentId], category_weights: DEFAULT_CATEGORY_WEIGHTS,
      })
      setResult(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div>
      <h1>Run a match</h1>
      <div className="card">
        <form onSubmit={handleRun}>
          <label className="field">Vacancy ID
            <input value={vacancyId} onChange={(e) => setVacancyId(e.target.value)} required />
          </label>
          <label className="field">Candidate (talent) ID
            <input value={talentId} onChange={(e) => setTalentId(e.target.value)} required />
          </label>
          <button type="submit" disabled={running}>{running ? 'Running...' : 'Run match'}</button>
        </form>
        {error && <p className="hint-error">{error}</p>}
      </div>
      {result && (
        <div className="card match-result">
          <h2>Result</h2>
          <pre>{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </div>
  )
}
