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

const STATUS_LABELS = {
  never_run: 'Never run', running: 'Running...', succeeded: 'Succeeded', failed: 'Failed', static: 'Static',
}

function StatusBadge({ status }) {
  const cls = status === 'failed' ? 'hint-error' : status === 'succeeded' ? 'hint-success' : ''
  return <span className={cls} style={{ padding: '2px 6px', borderRadius: 4 }}>{STATUS_LABELS[status] || status}</span>
}

function summarizeResult(task) {
  if (task.status === 'failed') return task.error_message
  if (task.status === 'static') return task.note
  if (task.result_summary && typeof task.result_summary === 'object') {
    return Object.entries(task.result_summary)
      .filter(([, v]) => typeof v !== 'object')
      .map(([k, v]) => `${k}: ${v}`)
      .join(', ')
  }
  return null
}

function ManualProcesses() {
  const [tasks, setTasks] = useState(null)
  const [error, setError] = useState(null)
  const [pending, setPending] = useState({})

  const load = () => api.getTaskStatus().then(setTasks).catch((err) => setError(err.message))

  useEffect(() => { load() }, [])

  useEffect(() => {
    if (!tasks || !tasks.some((t) => t.status === 'running')) return undefined
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [tasks])

  const runOne = async (taskName) => {
    setPending((p) => ({ ...p, [taskName]: true }))
    try {
      await api.runTask(taskName)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setPending((p) => ({ ...p, [taskName]: false }))
    }
  }

  const runAllReferenceRefresh = async () => {
    setPending((p) => ({ ...p, __refreshAll: true }))
    try {
      await api.runAllReferenceRefresh()
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setPending((p) => ({ ...p, __refreshAll: false }))
    }
  }

  if (error) return <p className="hint-error">Could not load task status: {error}</p>
  if (!tasks) return <p>Loading...</p>

  const referenceTasks = tasks.filter((t) => t.task_name.startsWith('reference_'))
  const otherTasks = tasks.filter((t) => !t.task_name.startsWith('reference_'))

  const row = (task) => (
    <tr key={task.task_name}>
      <td>{task.label}</td>
      <td><StatusBadge status={task.status} /></td>
      <td>{task.started_at ? new Date(task.started_at).toLocaleString() : 'never'}</td>
      <td style={{ maxWidth: 320, fontSize: 12 }}>{summarizeResult(task) ?? '--'}</td>
      <td>
        {task.refreshable && (
          <button type="button" disabled={task.status === 'running' || pending[task.task_name]}
            onClick={() => runOne(task.task_name)}>
            {task.status === 'running' ? 'Running...' : 'Run now'}
          </button>
        )}
      </td>
    </tr>
  )

  return (
    <div>
      <h3 className="category-heading">Manual processes</h3>
      <table className="report-table">
        <thead><tr><th>Process</th><th>Status</th><th>Last run</th><th>Result</th><th></th></tr></thead>
        <tbody>
          {referenceTasks.map(row)}
          {otherTasks.map(row)}
        </tbody>
      </table>
      <button type="button" className="secondary" style={{ marginTop: 8 }}
        disabled={pending.__refreshAll || referenceTasks.some((t) => t.status === 'running')}
        onClick={runAllReferenceRefresh}>
        {pending.__refreshAll ? 'Starting...' : 'Refresh all reference data'}
      </button>
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
      <ManualProcesses />
    </div>
  )
}
