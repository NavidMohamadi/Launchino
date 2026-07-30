// Small shared form-field primitives -- originally defined only inside
// valueEditors/index.jsx (for the 5 original single-value categories); moved
// here so the new repeatable-entry pages (Education/Capabilities/Task
// History, Phase 4) reuse the same components instead of a second copy.
export function TextField({ label, value, onChange, placeholder, required = false }) {
  return (
    <label className="field">
      {label}{required && <span aria-hidden="true"> *</span>}
      <input
        type="text" value={value ?? ''} placeholder={placeholder} required={required}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  )
}

// options may be plain strings (value === label, the original shape) or
// {value, label} objects (Phase 5 -- e.g. ISCED-F codes, where the code
// itself isn't a helpful thing to show the user, only its name is).
export function Select({ label, value, options, onChange }) {
  const normalised = options.map((o) => (typeof o === 'string' ? { value: o, label: o } : o))
  return (
    <label className="field">
      {label}
      <select value={value ?? ''} onChange={(e) => onChange(e.target.value)}>
        <option value="" disabled>-- choose --</option>
        {normalised.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  )
}

export function CheckboxGroup({ label, value, options, onChange }) {
  const selected = new Set(value || [])
  const toggle = (opt) => {
    const next = new Set(selected)
    next.has(opt) ? next.delete(opt) : next.add(opt)
    onChange([...next])
  }
  return (
    <fieldset className="field">
      <legend>{label}</legend>
      {options.map((opt) => (
        <label key={opt} className="checkbox">
          <input type="checkbox" checked={selected.has(opt)} onChange={() => toggle(opt)} />
          {opt}
        </label>
      ))}
    </fieldset>
  )
}

export function DateField({ label, value, onChange }) {
  return (
    <label className="field">
      {label}
      <input type="date" value={value ?? ''} onChange={(e) => onChange(e.target.value || null)} />
    </label>
  )
}
