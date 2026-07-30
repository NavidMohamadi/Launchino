import { useEffect, useRef, useState } from 'react'

// Debounced free-text-with-suggestions input, backing Education's
// institution/programme fields (Phase 4 -- api/routers/reference.py's
// /reference/institutions and /reference/programs, against the ROR/DUO
// datasets bundled in Phase 0). Free text is always accepted as-is (the
// "other" fallback from the original design -- see PROJECT_NOTES.md): this
// never blocks on picking a suggestion, it only offers one.
export default function SearchAutocomplete({ label, value, onChange, searchFn, getOptionLabel, placeholder, onBlur }) {
  const [query, setQuery] = useState(value || '')
  const [options, setOptions] = useState([])
  const [open, setOpen] = useState(false)
  const debounceRef = useRef(null)

  useEffect(() => { setQuery(value || '') }, [value])

  function handleInput(text) {
    setQuery(text)
    onChange(text, null)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (text.trim().length < 2) {
      setOptions([])
      setOpen(false)
      return
    }
    debounceRef.current = setTimeout(() => {
      searchFn(text).then((results) => {
        setOptions(results)
        setOpen(true)
      }).catch(() => setOptions([]))
    }, 300)
  }

  function pick(option) {
    const optionLabel = getOptionLabel(option)
    setQuery(optionLabel)
    setOpen(false)
    onChange(optionLabel, option)
  }

  return (
    <label className="field" style={{ position: 'relative' }}>
      {label}
      <input
        type="text" value={query} placeholder={placeholder}
        onChange={(e) => handleInput(e.target.value)}
        onFocus={() => { if (options.length) setOpen(true) }}
        onBlur={() => { setTimeout(() => setOpen(false), 150); if (onBlur) onBlur(query) }}
      />
      {open && options.length > 0 && (
        <ul className="autocomplete-list">
          {options.map((opt, i) => (
            <li key={i} onMouseDown={() => pick(opt)}>{getOptionLabel(opt)}</li>
          ))}
        </ul>
      )}
    </label>
  )
}
