// Tri-state answer control matching the Fit Dictionary's real value states
// (schemas.py's ValueStatus): answered / unknown / not_scored -- not a
// simple yes/no. When "answered" is picked, renders whatever value editor
// is passed as children. When "unknown"/"not_scored" is picked, collects the
// required reason code (schemas.py's ElementValueState requires exactly one
// of unknown_reason/not_scored_reason depending on status; the backend
// re-validates this regardless of what the frontend sends).

const UNKNOWN_REASONS = [
  'candidate_not_answered', 'vacancy_not_specified', 'candidate_declined',
  'assessment_not_completed', 'conflicting_information', 'requires_verification',
]

const NOT_SCORED_REASONS = ['not_top_five', 'not_activated_for_vacancy', 'out_of_scope_by_design']

function defaultUnknownReason(side) {
  return side === 'vacancy' ? 'vacancy_not_specified' : 'candidate_not_answered'
}

function defaultNotScoredReason(side) {
  return side === 'vacancy' ? 'not_activated_for_vacancy' : 'not_top_five'
}

export default function TriStateAnswer({ side, answer, onChange, children }) {
  const status = answer.value_status || 'answered'

  const setStatus = (nextStatus) => {
    if (nextStatus === 'answered') {
      onChange({ ...answer, value_status: 'answered', unknown_reason: null, not_scored_reason: null })
    } else if (nextStatus === 'unknown') {
      onChange({
        ...answer, value_status: 'unknown', value: {},
        unknown_reason: answer.unknown_reason || defaultUnknownReason(side), not_scored_reason: null,
      })
    } else {
      onChange({
        ...answer, value_status: 'not_scored', value: {},
        not_scored_reason: answer.not_scored_reason || defaultNotScoredReason(side), unknown_reason: null,
      })
    }
  }

  return (
    <div className="tri-state">
      <div className="tri-state-toggle">
        {['answered', 'unknown', 'not_scored'].map((option) => (
          <label key={option} className={status === option ? 'active' : ''}>
            <input
              type="radio"
              name={`status-${answer.element_id}`}
              checked={status === option}
              onChange={() => setStatus(option)}
            />
            {option === 'answered' ? 'Answered' : option === 'unknown' ? "Don't know" : 'Not applicable'}
          </label>
        ))}
      </div>

      {status === 'answered' && <div className="tri-state-value">{children}</div>}

      {status === 'unknown' && (
        <select
          value={answer.unknown_reason || defaultUnknownReason(side)}
          onChange={(e) => onChange({ ...answer, unknown_reason: e.target.value })}
        >
          {UNKNOWN_REASONS.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      )}

      {status === 'not_scored' && (
        <select
          value={answer.not_scored_reason || defaultNotScoredReason(side)}
          onChange={(e) => onChange({ ...answer, not_scored_reason: e.target.value })}
        >
          {NOT_SCORED_REASONS.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      )}
    </div>
  )
}
