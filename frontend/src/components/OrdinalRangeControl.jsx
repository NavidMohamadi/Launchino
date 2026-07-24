// Stepped 1-5 input for comparator_key="ordinal_range" elements.
// Candidate side: preferred_min/max + tolerable_min/max (schemas.py's OrdinalRange:
// the tolerable range must contain the preferred range -- enforced authoritatively
// by the backend; this only gives an inline hint, it doesn't re-derive the rule).
// Vacancy side: a single "actual" 1-5 value.

function Stepper({ label, value, onChange }) {
  return (
    <label className="stepper">
      {label}
      <input
        type="range" min={1} max={5} step={1} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <span className="stepper-value">{value}</span>
    </label>
  )
}

export function OrdinalRangeCandidateControl({ value, onChange }) {
  const v = {
    preferred_min: value.preferred_min ?? 3, preferred_max: value.preferred_max ?? 3,
    tolerable_min: value.tolerable_min ?? 2, tolerable_max: value.tolerable_max ?? 4,
    ...value,
  }
  const update = (patch) => onChange({ ...v, ...patch })
  const outOfBounds = v.tolerable_min > v.preferred_min || v.preferred_max > v.tolerable_max
    || v.preferred_min > v.preferred_max || v.tolerable_min > v.tolerable_max

  return (
    <div className="ordinal-range">
      <Stepper label="Preferred min" value={v.preferred_min} onChange={(n) => update({ preferred_min: n })} />
      <Stepper label="Preferred max" value={v.preferred_max} onChange={(n) => update({ preferred_max: n })} />
      <Stepper label="Tolerable min" value={v.tolerable_min} onChange={(n) => update({ tolerable_min: n })} />
      <Stepper label="Tolerable max" value={v.tolerable_max} onChange={(n) => update({ tolerable_max: n })} />
      {outOfBounds && (
        <p className="hint-warning">
          The tolerable range should fully contain the preferred range -- the server will reject this otherwise.
        </p>
      )}
    </div>
  )
}

export function OrdinalActualControl({ value, onChange }) {
  const actual = typeof value.actual === 'number' ? value.actual : 3
  return (
    <div className="ordinal-range">
      <Stepper label="Actual level" value={actual} onChange={(n) => onChange({ ...value, actual: n })} />
    </div>
  )
}
