import SearchAutocomplete from './SearchAutocomplete'
import { Select } from './formFields'

// Generic repeatable "this vacancy requires X" list editor -- backs
// CAP-SKILLS/TASK-EXPERIENCE/EDU-HISTORY's vacancy-side
// required_skills/required_occupations/required_education (Phase 5, see
// PROJECT_NOTES.md). Two picker modes:
//   - "search": search-and-pick against a large reference list (ESCO
//     skills/occupations, via /reference/skills|occupations).
//   - "select": choose from a small, complete, fixed list (ISCED-F's 29
//     fields, via /reference/isced-fields) -- a plain dropdown reads better
//     than a search box when every option already fits on screen.
// Deliberately NOT routed through AI mapping the way candidate self-reported
// skills are (api/mapping_service.py): a company is authoritatively DEFINING
// a requirement, not self-reporting an ambiguous personal fact, so picking
// an exact code directly is more appropriate here.
export default function RequirementListEditor({
  entries, onChange, codeField, textField, picker, requirementLevelField, requirementLevels,
}) {
  function updateEntry(index, patch) {
    onChange(entries.map((entry, i) => (i === index ? { ...entry, ...patch } : entry)))
  }

  function removeEntry(index) {
    onChange(entries.filter((_, i) => i !== index))
  }

  function addEntry() {
    const blank = { [codeField]: null, requirement: 'required' }
    if (textField) blank[textField] = ''
    if (requirementLevelField) blank[requirementLevelField] = requirementLevels[0]
    onChange([...entries, blank])
  }

  return (
    <div className="field-group">
      {entries.map((entry, index) => (
        <div key={index} className="entry-card">
          <button type="button" className="entry-card-remove" onClick={() => removeEntry(index)}>Remove</button>
          <div className="field-group">
            {picker.mode === 'search' && (
              <SearchAutocomplete
                label={picker.label} value={entry[textField]} searchFn={picker.searchFn}
                getOptionLabel={(o) => o.label} placeholder={picker.placeholder}
                onChange={(text, option) => updateEntry(index, {
                  [textField]: text, [codeField]: option ? option.uri : null,
                })}
              />
            )}
            {picker.mode === 'select' && (
              <Select
                label={picker.label} value={entry[codeField]} options={picker.options}
                onChange={(code) => updateEntry(index, { [codeField]: code })}
              />
            )}
            {requirementLevelField && (
              <Select
                label="Level" value={entry[requirementLevelField]} options={requirementLevels}
                onChange={(v) => updateEntry(index, { [requirementLevelField]: v })}
              />
            )}
            <Select
              label="Requirement" value={entry.requirement} options={['required', 'preferred']}
              onChange={(v) => updateEntry(index, { requirement: v })}
            />
          </div>
        </div>
      ))}
      <button type="button" onClick={addEntry}>+ Add requirement</button>
    </div>
  )
}
