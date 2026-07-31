import { useState } from 'react'
import * as api from '../api'
import { Select, DateField } from './formFields'
import SearchAutocomplete from './SearchAutocomplete'

const LEVELS = ['secondary', 'vocational', 'bachelor', 'master', 'phd', 'other']
const STATUSES = ['completed', 'currently_studying', 'did_not_complete']

export function blankEducationEntry() {
  return {
    level: 'bachelor', institution: { ror_id: null, name: '' }, program: '',
    field: { isced_code: null, confidence: null }, start_date: null, end_date: null, status: 'completed',
  }
}

// Shared between EducationPage.jsx (the standalone Education category page)
// and QuickStartCvCard.jsx (the one-time dashboard CV step, which reviews
// extracted EDU-HISTORY entries alongside phone/Practical fit) -- same
// entry-editing UI, not two copies.
export default function EducationEntryEditor({ talentId, entries, onChange }) {
  const [programMappings, setProgramMappings] = useState({})

  function updateEntry(index, patch) {
    onChange(entries.map((e, i) => (i === index ? { ...e, ...patch } : e)))
  }

  function removeEntry(index) {
    onChange(entries.filter((_, i) => i !== index))
    setProgramMappings((prev) => { const next = { ...prev }; delete next[index]; return next })
  }

  async function mapProgramField(index, programText) {
    if (!programText || !programText.trim()) return
    try {
      const result = await api.mapProgram(talentId, programText)
      updateEntry(index, {
        field: { isced_code: result.matched_code, confidence: result.confidence },
      })
      setProgramMappings((prev) => ({ ...prev, [index]: result }))
    } catch {
      // Mapping is a best-effort enrichment, not a blocker -- the raw programme
      // text is still saved either way, just without an ISCED-F code.
    }
  }

  return (
    <>
      {entries.map((entry, index) => {
        const mapping = programMappings[index]
        return (
          <div key={index} className="entry-card">
            <button type="button" className="entry-card-remove" onClick={() => removeEntry(index)}>Remove</button>
            <div className="field-group">
              <Select label="Level" value={entry.level} options={LEVELS} onChange={(v) => updateEntry(index, { level: v })} />
              <SearchAutocomplete
                label="Institution" value={entry.institution.name}
                searchFn={api.searchInstitutions}
                getOptionLabel={(o) => o.name}
                placeholder="Start typing your institution..."
                onChange={(text, option) => updateEntry(index, { institution: { name: text, ror_id: option?.ror_id ?? null } })}
              />
              <SearchAutocomplete
                label="Programme" value={entry.program}
                searchFn={api.searchPrograms}
                getOptionLabel={(o) => o.name}
                placeholder="Start typing your programme..."
                onChange={(text) => updateEntry(index, { program: text })}
                onBlur={(text) => mapProgramField(index, text)}
              />
              {mapping && (
                <p className="confidence-flag">
                  {mapping.matched_label
                    ? `Matched field of study: ${mapping.matched_label}${mapping.requires_confirmation ? ' (please double-check this)' : ''}`
                    : 'Could not automatically classify this programme\'s field of study -- that\'s fine, it\'s still saved.'}
                </p>
              )}
              <DateField label="Start date" value={entry.start_date} onChange={(v) => updateEntry(index, { start_date: v })} />
              <DateField label="End date" value={entry.end_date} onChange={(v) => updateEntry(index, { end_date: v })} />
              <Select label="Status" value={entry.status} options={STATUSES} onChange={(v) => updateEntry(index, { status: v })} />
            </div>
          </div>
        )
      })}
      <button type="button" onClick={() => onChange([...entries, blankEducationEntry()])}>+ Add education</button>
    </>
  )
}
