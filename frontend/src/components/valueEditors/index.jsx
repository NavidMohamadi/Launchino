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
import { CheckboxGroup, DateField, Select, TextField } from '../formFields'

// --- ordinal_requirement (TEAM-*): 0-4 level ---
function OrdinalRequirementCandidate({ value, onChange }) {
  return (
    <div className="field-group">
      <Stepper04 label="Your level" value={value.level ?? 2} onChange={(n) => onChange({ ...value, level: n })} />
      <TextField label="Example" value={value.example} onChange={(v) => onChange({ ...value, example: v })} />
    </div>
  )
}
function OrdinalRequirementVacancy({ value, onChange }) {
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
    <RequirementListEditor
      entries={value.required_education || []}
      onChange={(entries) => onChange({ ...value, required_education: entries })}
      codeField="isced_code"
      picker={{ mode: 'select', label: 'Field of study', options: iscedFields }}
      requirementLevelField="level" requirementLevels={['secondary', 'vocational', 'bachelor', 'master', 'phd']}
    />
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
}

export function getValueEditor(comparatorKey, side) {
  const pair = VALUE_EDITORS[comparatorKey]
  if (!pair) return null
  return pair[side]
}
