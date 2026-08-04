// One editor pair (candidate/vacancy) per comparator_key actually used in
// data/fit_dictionary_starter.json -- a closed, known set, not an
// open-ended renderer. tagged_list_overlap_skills/_occupation/_education
// (Phase 5) are vacancy-side only here -- their candidate side is handled
// by dedicated pages (Education/Capabilities/Task History, Phase 4) that
// bypass this registry entirely, not by an entry registered here.
// Each editor only produces the value dict; TriStateAnswer / ElementQuestion
// own the value_status/reason wrapper around it.
import { useEffect, useState } from 'react'
import * as api from '../../api'
import { OrdinalActualControl, OrdinalRangeCandidateControl } from '../OrdinalRangeControl'
import RequirementListEditor from '../RequirementListEditor'
import SearchAutocomplete from '../SearchAutocomplete'
import { CheckboxGroup, DateField, Select, TextField } from '../formFields'

// A slider always renders SOME number (there is no meaningful "empty" state
// for <input type=range>, unlike a Select's "-- choose --" or an unchecked
// checkbox) -- so the number shown on first render must become the real
// answer immediately, not just a display fallback the user has to actively
// confirm by dragging. Without this, a candidate/company who accepts what's
// already shown and submits without touching the slider silently loses that
// answer: CategorySurveyPage/VacancyWorkshopPage only include an element_id
// in the submission once something has called onChange for it (real bug
// found via live browser verification, see PROJECT_NOTES.md's Phase 5 entry
// -- not hypothetical, reproduced with values_stored: 0 on a real submit).
function useSeedDefaults(value, onChange, defaults) {
  useEffect(() => {
    if (Object.keys(defaults).some((k) => value[k] === undefined)) onChange({ ...defaults, ...value })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}

// --- ordinal_requirement (TEAM-*): 0-4 level ---
// No per-element "Example" field on the candidate side: `example` exists only
// in these elements' vacancy_value_schema, never their candidate_value_schema
// (data/fit_dictionary_starter.json) -- the candidate's illustrative example
// is the separate TEAM-EVIDENCE element, one free-text answer covering all six
// self-ratings, deliberately not six per-element repetitions of the same ask.
// The field was here but unreachable until Phase 7 made these six visible
// candidate-side, so it never actually wrote off-schema data; see
// PROJECT_NOTES.md's Phase 7 entry.
function OrdinalRequirementCandidate({ value, onChange }) {
  useSeedDefaults(value, onChange, { level: 2 })
  return (
    <div className="field-group">
      <Stepper04 label="Your level" value={value.level ?? 2} onChange={(n) => onChange({ ...value, level: n })} />
    </div>
  )
}
function OrdinalRequirementVacancy({ value, onChange }) {
  useSeedDefaults(value, onChange, { required_level: 2 })
  return (
    <div className="field-group">
      <Stepper04 label="Required level" value={value.required_level ?? 2} onChange={(n) => onChange({ ...value, required_level: n })} />
      <TextField label="Example" value={value.example} onChange={(v) => onChange({ ...value, example: v })} />
    </div>
  )
}
function Stepper04({ label, value, onChange }) {
  return (
    <label className="stepper">
      {label}
      <input type="range" min={0} max={4} step={1} value={value} onChange={(e) => onChange(Number(e.target.value))} />
      <span className="stepper-value">{value}</span>
    </label>
  )
}

// --- semantic_overlap (CAREER-*): ranked free-text list ---
function SemanticOverlapEditor({ value, onChange }) {
  const values = value.values || ['']
  const setAt = (i, v) => {
    const next = [...values]; next[i] = v
    onChange({ ...value, values: next, ranked: true })
  }
  return (
    <div className="field-group">
      {values.map((v, i) => (
        <TextField key={i} label={`#${i + 1}`} value={v} onChange={(v2) => setAt(i, v2)} />
      ))}
      <button type="button" onClick={() => onChange({ ...value, values: [...values, ''], ranked: true })}>
        + add another
      </button>
    </div>
  )
}

// --- visa_sponsorship (PRACT-SPONSOR) ---
function VisaSponsorshipCandidate({ value, onChange }) {
  return <Select label="Sponsorship" value={value.requirement} options={['required', 'not_required', 'not_sure']}
    onChange={(v) => onChange({ ...value, requirement: v })} />
}
function VisaSponsorshipVacancy({ value, onChange }) {
  return (
    <div className="field-group">
      <Select label="Policy" value={value.policy} options={['available', 'conditional', 'unavailable', 'not_specified']}
        onChange={(v) => onChange({ ...value, policy: v })} />
      <TextField label="Conditions" value={value.conditions} onChange={(v) => onChange({ ...value, conditions: v })} />
    </div>
  )
}

// --- country_presence (PRACT-COUNTRY) ---
function CountryPresenceCandidate({ value, onChange }) {
  return (
    <div className="field-group">
      <TextField label="Current country" value={value.current_country} onChange={(v) => onChange({ ...value, current_country: v })} />
      <Select label="Presence" value={value.presence_relative_to_vacancy} options={['in_country', 'outside_country', 'unknown']}
        onChange={(v) => onChange({ ...value, presence_relative_to_vacancy: v })} />
    </div>
  )
}
function CountryPresenceVacancy({ value, onChange }) {
  return (
    <div className="field-group">
      <TextField label="Employment country" value={value.employment_country} onChange={(v) => onChange({ ...value, employment_country: v })} />
      <Select label="Condition" value={value.condition} options={['required', 'preferred', 'open', 'not_specified']}
        onChange={(v) => onChange({ ...value, condition: v })} />
    </div>
  )
}

// --- availability (PRACT-START) ---
function AvailabilityCandidate({ value, onChange }) {
  return <DateField label="Earliest start" value={value.earliest_start} onChange={(v) => onChange({ ...value, earliest_start: v })} />
}
function AvailabilityVacancy({ value, onChange }) {
  return (
    <div className="field-group">
      <DateField label="Preferred start" value={value.preferred_start} onChange={(v) => onChange({ ...value, preferred_start: v })} />
      <DateField label="Latest acceptable start" value={value.latest_acceptable_start} onChange={(v) => onChange({ ...value, latest_acceptable_start: v })} />
    </div>
  )
}

// --- language_level (PRACT-LANG) ---
const LANGUAGE_LEVELS = ['basic', 'working', 'professional', 'fluent', 'native_or_equivalent']

// Schema says value.languages is a { languageName: level } map, but AI extraction
// sometimes returns a [{ language, level }, ...] list instead; normalise defensively
// so the review screen never crashes on whichever shape actually comes back.
function normaliseLanguages(languages) {
  if (Array.isArray(languages)) {
    const map = {}
    for (const entry of languages) {
      if (entry && typeof entry === 'object' && entry.language) map[entry.language] = entry.level
    }
    return map
  }
  return languages || {}
}

function LanguageLevelCandidate({ value, onChange }) {
  const languages = normaliseLanguages(value.languages)
  const [lang, setLang] = useState('')
  return (
    <div className="field-group">
      {Object.entries(languages).map(([name, level]) => (
        <div key={name} className="language-row">
          <span>{name}: {typeof level === 'string' ? level : JSON.stringify(level)}</span>
        </div>
      ))}
      <div className="language-row">
        <input type="text" placeholder="language" value={lang} onChange={(e) => setLang(e.target.value)} />
        <select onChange={(e) => {
          if (lang && e.target.value) {
            onChange({ ...value, languages: { ...languages, [lang]: e.target.value } })
            setLang('')
          }
        }} defaultValue="">
          <option value="" disabled>add level</option>
          {LANGUAGE_LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
      </div>
    </div>
  )
}
function LanguageLevelVacancy({ value, onChange }) {
  return (
    <div className="field-group">
      <TextField label="Language" value={value.language} onChange={(v) => onChange({ ...value, language: v })} />
      <Select label="Minimum level" value={value.minimum_level} options={LANGUAGE_LEVELS} onChange={(v) => onChange({ ...value, minimum_level: v })} />
      <Select label="Required or preferred" value={value.status} options={['required', 'preferred', 'not_specified']} onChange={(v) => onChange({ ...value, status: v })} />
      <TextField label="Reason" value={value.reason} onChange={(v) => onChange({ ...value, reason: v })} />
    </div>
  )
}

// --- contract_set / work_mode_set (PRACT-CONTRACT / PRACT-WORKMODE) ---
function ContractSetCandidate({ value, onChange }) {
  return <CheckboxGroup label="Acceptable contract types" value={value.acceptable}
    options={['internship', 'full_time', 'traineeship', 'project', 'other']}
    onChange={(v) => onChange({ ...value, acceptable: v })} />
}
function ContractSetVacancy({ value, onChange }) {
  const offered = (value.description && value.description.offered) || []
  return <CheckboxGroup label="Offered contract types" value={offered}
    options={['internship', 'full_time', 'traineeship', 'project', 'other']}
    onChange={(v) => onChange({ ...value, description: { offered: v } })} />
}
function WorkModeSetCandidate({ value, onChange }) {
  return <CheckboxGroup label="Acceptable work arrangements" value={value.acceptable}
    options={['on_site', 'hybrid', 'remote']} onChange={(v) => onChange({ ...value, acceptable: v })} />
}
function WorkModeSetVacancy({ value, onChange }) {
  const offered = (value.description && value.description.offered) || []
  return <CheckboxGroup label="Actual work arrangement(s)" value={offered}
    options={['on_site', 'hybrid', 'remote', 'flexible']}
    onChange={(v) => onChange({ ...value, description: { offered: v } })} />
}

// --- work_type_set (PRACT-WORKTYPE, Phase 4) -- distinct from work_mode_set
// above: this is employment TYPE (full-time/internship/student job/part-time),
// not work-location arrangement.
function WorkTypeSetCandidate({ value, onChange }) {
  return <CheckboxGroup label="Acceptable work type(s)" value={value.acceptable}
    options={['full_time', 'internship', 'student_job', 'part_time']}
    onChange={(v) => onChange({ ...value, acceptable: v })} />
}
function WorkTypeSetVacancy({ value, onChange }) {
  const offered = (value.description && value.description.offered) || []
  return <CheckboxGroup label="Work type(s) offered" value={offered}
    options={['full_time', 'internship', 'student_job', 'part_time']}
    onChange={(v) => onChange({ ...value, description: { offered: v } })} />
}


// --- ordinal_distance (v3 redesign, Phase 5 -- see PROJECT_NOTES.md): a
// single 1-5 value on both sides (ENV, RIASEC, TEAM-COLLAB-INTENSITY) --
// simpler than ordinal_range's 4-value preferred/tolerable band, since
// Family 2's symmetric-distance formula only needs one number per side.
function Stepper15({ label, value, onChange }) {
  return (
    <label className="stepper">
      {label}
      <input type="range" min={1} max={5} step={1} value={value} onChange={(e) => onChange(Number(e.target.value))} />
      <span className="stepper-value">{value}</span>
    </label>
  )
}
function OrdinalDistanceCandidate({ value, onChange }) {
  useSeedDefaults(value, onChange, { level: 3 })
  return <Stepper15 label="Your level" value={value.level ?? 3} onChange={(n) => onChange({ ...value, level: n })} />
}
function OrdinalDistanceVacancy({ value, onChange }) {
  useSeedDefaults(value, onChange, { required_level: 3 })
  return <Stepper15 label="Actual level" value={value.required_level ?? 3} onChange={(n) => onChange({ ...value, required_level: n })} />
}

// --- motivation_preferred_minimum (v3 redesign, Phase 5): the candidate
// states a preferred AND a minimum-acceptable 1-5 level for a selected
// priority (selected/priority_rank are set by CategorySurveyPage's MOT
// checkbox handling, not this editor -- spread through unchanged here);
// the vacancy supplies one actual 1-5 value.
function MotivationPreferredMinimumCandidate({ value, onChange }) {
  useSeedDefaults(value, onChange, { preferred_level: 3, minimum_acceptable_level: 2 })
  return (
    <div className="field-group">
      <Stepper15 label="Preferred level" value={value.preferred_level ?? 3} onChange={(n) => onChange({ ...value, preferred_level: n })} />
      <Stepper15 label="Lowest you'd accept" value={value.minimum_acceptable_level ?? 2} onChange={(n) => onChange({ ...value, minimum_acceptable_level: n })} />
    </div>
  )
}
function MotivationPreferredMinimumVacancy({ value, onChange }) {
  useSeedDefaults(value, onChange, { actual_level: 3 })
  return <Stepper15 label="Actual level" value={value.actual_level ?? 3} onChange={(n) => onChange({ ...value, actual_level: n })} />
}

// --- esco_occupation_pick (v3 redesign, Phase 5): CAREER-PRIMARY-ROLE/
// SECONDARY-ROLE. Plain-language search-and-pick against ESCO occupations
// (same picker as the vacancy-side required-occupations editor above) --
// ESCO/the uri are never shown to the candidate, only the label they typed
// or picked. raw_text is always kept even without a picked match (mirrors
// EDU-HISTORY's own established pattern -- a candidate's original free text
// is never lost just because nothing was picked from the list); picking a
// real suggestion is a direct, human-confirmed match, not an AI guess, so it
// gets confidence 1.0 rather than null.
function OccupationPickCandidate({ value, onChange }) {
  const occupation = value.occupation || {}
  return (
    <div className="field-group">
      <SearchAutocomplete
        label="Target occupation" value={occupation.raw_text} searchFn={api.searchOccupations}
        getOptionLabel={(o) => o.label} placeholder="Start typing an occupation..."
        onChange={(text, option) => onChange({
          ...value,
          occupation: {
            raw_text: text, esco_uri: option ? option.uri : null, label: option ? option.label : null,
            confidence: option ? 1.0 : null,
          },
        })}
      />
      <label className="checkbox">
        <input type="checkbox" checked={!!value.still_exploring}
          onChange={(e) => onChange({ ...value, still_exploring: e.target.checked })} />
        I'm still exploring options
      </label>
      <label className="checkbox">
        <input type="checkbox" checked={!!value.open_to_adjacent}
          onChange={(e) => onChange({ ...value, open_to_adjacent: e.target.checked })} />
        Open to adjacent roles
      </label>
    </div>
  )
}
function OccupationPickVacancy({ value, onChange }) {
  const occupation = value.occupation || {}
  return (
    <SearchAutocomplete
      label="Role family / occupational direction" value={occupation.label} searchFn={api.searchOccupations}
      getOptionLabel={(o) => o.label} placeholder="Start typing an occupation..."
      onChange={(text, option) => onChange({
        ...value, occupation: { esco_uri: option ? option.uri : null, label: option ? option.label : text },
      })}
    />
  )
}

// --- nace_industry_overlap (v3 redesign, Phase 5): CAREER-INDUSTRIES.
// NACE is mapped at section level only in this system (21 sections, no
// sub-hierarchy -- see data/reference/nace_industries.json), small enough
// to pick from a plain dropdown rather than a search box (same reasoning
// as RequiredEducationVacancy's ISCED-F picker above).
function useNaceOptions() {
  const [options, setOptions] = useState([])
  useEffect(() => { api.getNaceSections().then((sections) => setOptions(sections.map((s) => ({ value: s.code, label: s.label })))) }, [])
  return options
}
function IndustriesCandidate({ value, onChange }) {
  const options = useNaceOptions()
  const industries = value.industries || []
  function updateAt(i, code) {
    const match = options.find((o) => o.value === code)
    const next = [...industries]
    next[i] = { raw_text: match ? match.label : null, nace_code: code || null, label: match ? match.label : null, confidence: code ? 1.0 : null }
    onChange({ ...value, industries: next })
  }
  return (
    <div className="field-group">
      {industries.map((entry, i) => (
        <div key={i} className="entry-card">
          <button type="button" className="entry-card-remove" onClick={() => onChange({ ...value, industries: industries.filter((_, j) => j !== i) })}>Remove</button>
          <Select label="Industry" value={entry.nace_code} options={options} onChange={(code) => updateAt(i, code)} />
        </div>
      ))}
      <button type="button" onClick={() => onChange({ ...value, industries: [...industries, { raw_text: null, nace_code: null, label: null, confidence: null }] })}>
        + Add industry
      </button>
    </div>
  )
}
function IndustriesVacancy({ value, onChange }) {
  const options = useNaceOptions()
  const industries = value.industries || []
  function updateAt(i, code) {
    const match = options.find((o) => o.value === code)
    const next = [...industries]
    next[i] = { nace_code: code || null, label: match ? match.label : null }
    onChange({ ...value, industries: next })
  }
  return (
    <div className="field-group">
      {industries.map((entry, i) => (
        <div key={i} className="entry-card">
          <button type="button" className="entry-card-remove" onClick={() => onChange({ ...value, industries: industries.filter((_, j) => j !== i) })}>Remove</button>
          <Select label="Industry" value={entry.nace_code} options={options} onChange={(code) => updateAt(i, code)} />
        </div>
      ))}
      <button type="button" onClick={() => onChange({ ...value, industries: [...industries, { nace_code: null, label: null }] })}>
        + Add industry
      </button>
    </div>
  )
}

// --- unscored (v3 redesign, Phase 5): CAREER-NARRATIVE, CAREER-DEVELOPMENT,
// TEAM-EVIDENCE -- free text, stored for human review, never scored (see
// PROJECT_NOTES.md's Phase 2 entry -- matching_service.py excludes these
// from matching entirely). Candidate side only: VacancyWorkshopPage filters
// comparator_key "unscored" out of its rendered element list entirely,
// since there is genuinely nothing for a vacancy to answer here.
function UnscoredTextEditor({ value, onChange }) {
  return (
    <label className="field">
      <textarea className="cv-input" value={value.text || ''} onChange={(e) => onChange({ ...value, text: e.target.value })} />
    </label>
  )
}

// --- tagged_list_overlap_skills/_occupation/_education (Phase 5) --
// vacancy-side only; see this file's own top-of-file comment for why there
// is no candidate-side entry for these three keys.
function RequiredSkillsVacancy({ value, onChange }) {
  return (
    <RequirementListEditor
      entries={value.required_skills || []}
      onChange={(entries) => onChange({ ...value, required_skills: entries })}
      codeField="esco_uri" textField="skill"
      picker={{ mode: 'search', label: 'Skill', searchFn: api.searchSkills, placeholder: 'Start typing a required skill...' }}
      requirementLevelField="level" requirementLevels={['beginner', 'intermediate', 'advanced', 'expert']}
    />
  )
}

function RequiredOccupationsVacancy({ value, onChange }) {
  return (
    <RequirementListEditor
      entries={value.required_occupations || []}
      onChange={(entries) => onChange({ ...value, required_occupations: entries })}
      codeField="esco_uri" textField="occupation"
      picker={{ mode: 'search', label: 'Occupation', searchFn: api.searchOccupations, placeholder: 'Start typing a required occupation...' }}
    />
  )
}

function RequiredEducationVacancy({ value, onChange }) {
  const [iscedFields, setIscedFields] = useState([])
  useEffect(() => { api.getIscedFields().then((fields) => setIscedFields(fields.map((f) => ({ value: f.code, label: f.label })))) }, [])
  return (
    <div className="field-group">
      {/* v3 redesign (see PROJECT_NOTES.md): the conditional field-mismatch
          rule Family 1's education scoring depends on -- required caps the
          score hard on a field mismatch, preferred reduces it without
          capping, open ignores field entirely. Left unset, the comparator
          defaults to "open"; surfaced as an explicit, unset-by-default
          choice rather than silently deciding a real scoring behaviour for
          the company without them ever seeing it. */}
      <Select
        label="How strictly does this role require the field of study above?"
        value={value.education_field_requirement}
        options={[
          { value: 'required', label: 'Required -- a field mismatch rules the candidate out' },
          { value: 'preferred', label: 'Preferred -- a field mismatch reduces fit but does not rule anyone out' },
          { value: 'open', label: "Open -- field of study doesn't matter, only the level does" },
        ]}
        onChange={(v) => onChange({ ...value, education_field_requirement: v })}
      />
      <RequirementListEditor
        entries={value.required_education || []}
        onChange={(entries) => onChange({ ...value, required_education: entries })}
        codeField="isced_code"
        picker={{ mode: 'select', label: 'Field of study', options: iscedFields }}
        requirementLevelField="level" requirementLevels={['secondary', 'vocational', 'bachelor', 'master', 'phd']}
      />
    </div>
  )
}


export const VALUE_EDITORS = {
  ordinal_range: {
    candidate: OrdinalRangeCandidateControl,
    vacancy: OrdinalActualControl,
  },
  ordinal_requirement: { candidate: OrdinalRequirementCandidate, vacancy: OrdinalRequirementVacancy },
  semantic_overlap: { candidate: SemanticOverlapEditor, vacancy: SemanticOverlapEditor },
  visa_sponsorship: { candidate: VisaSponsorshipCandidate, vacancy: VisaSponsorshipVacancy },
  country_presence: { candidate: CountryPresenceCandidate, vacancy: CountryPresenceVacancy },
  availability: { candidate: AvailabilityCandidate, vacancy: AvailabilityVacancy },
  language_level: { candidate: LanguageLevelCandidate, vacancy: LanguageLevelVacancy },
  contract_set: { candidate: ContractSetCandidate, vacancy: ContractSetVacancy },
  work_mode_set: { candidate: WorkModeSetCandidate, vacancy: WorkModeSetVacancy },
  work_type_set: { candidate: WorkTypeSetCandidate, vacancy: WorkTypeSetVacancy },
  tagged_list_overlap_skills: { vacancy: RequiredSkillsVacancy },
  tagged_list_overlap_occupation: { vacancy: RequiredOccupationsVacancy },
  tagged_list_overlap_education: { vacancy: RequiredEducationVacancy },
  ordinal_distance: { candidate: OrdinalDistanceCandidate, vacancy: OrdinalDistanceVacancy },
  motivation_preferred_minimum: { candidate: MotivationPreferredMinimumCandidate, vacancy: MotivationPreferredMinimumVacancy },
  esco_occupation_pick: { candidate: OccupationPickCandidate, vacancy: OccupationPickVacancy },
  nace_industry_overlap: { candidate: IndustriesCandidate, vacancy: IndustriesVacancy },
  unscored: { candidate: UnscoredTextEditor },
}

export function getValueEditor(comparatorKey, side) {
  const pair = VALUE_EDITORS[comparatorKey]
  if (!pair) return null
  return pair[side]
}
