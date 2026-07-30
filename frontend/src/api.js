// Thin fetch wrapper around the existing FastAPI backend. Every function
// here maps 1:1 to an existing endpoint -- no new persistence logic, no new
// backend behavior invented on the frontend side.

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

class ApiError extends Error {
  constructor(message, { status, detail } = {}) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

// In-memory token, synced from AuthContext (which owns the localStorage copy) --
// api.js has no React state of its own, so every authenticated request just reads
// whatever AuthContext last told it via setAuthToken().
let _authToken = null
export function setAuthToken(token) {
  _authToken = token
}

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
  if (_authToken) headers.Authorization = `Bearer ${_authToken}`
  const response = await fetch(`${BASE_URL}${path}`, { ...options, headers })
  const text = await response.text()
  const data = text ? JSON.parse(text) : null
  if (!response.ok) {
    const detail = data?.detail
    const message = typeof detail === 'string' ? detail : JSON.stringify(detail ?? response.statusText)
    throw new ApiError(message, { status: response.status, detail })
  }
  return data
}

export const health = () => request('/health')

export const getFitDictionary = ({ candidateSelectedIds = [], vacancyActivatedIds = [] } = {}) => {
  const params = new URLSearchParams()
  if (candidateSelectedIds.length) params.set('candidate_selected_ids', candidateSelectedIds.join(','))
  if (vacancyActivatedIds.length) params.set('vacancy_activated_ids', vacancyActivatedIds.join(','))
  const qs = params.toString()
  return request(`/fit-dictionary${qs ? `?${qs}` : ''}`)
}

export const createCandidate = (payload) =>
  request('/candidates', { method: 'POST', body: JSON.stringify(payload) })

export const loginCandidate = (email, password) =>
  request('/candidates/login', { method: 'POST', body: JSON.stringify({ email, password }) })

export const getCandidate = (talentId) => request(`/candidates/${talentId}`)

export const updateCandidateSubscription = (talentId, payload) =>
  request(`/candidates/${talentId}/subscription`, { method: 'PATCH', body: JSON.stringify(payload) })

export const updateBasicInfo = (talentId, payload) =>
  request(`/candidates/${talentId}/basic-info`, { method: 'PATCH', body: JSON.stringify(payload) })

export const mapSkill = (talentId, term) =>
  request(`/candidates/${talentId}/map-skill`, { method: 'POST', body: JSON.stringify({ term }) })

export const mapOccupation = (talentId, term) =>
  request(`/candidates/${talentId}/map-occupation`, { method: 'POST', body: JSON.stringify({ term }) })

export const mapProgram = (talentId, term) =>
  request(`/candidates/${talentId}/map-program`, { method: 'POST', body: JSON.stringify({ term }) })

export const searchInstitutions = (q) => request(`/reference/institutions?q=${encodeURIComponent(q)}`)

export const searchPrograms = (q) => request(`/reference/programs?q=${encodeURIComponent(q)}`)

export const searchSkills = (q) => request(`/reference/skills?q=${encodeURIComponent(q)}`)

export const searchOccupations = (q) => request(`/reference/occupations?q=${encodeURIComponent(q)}`)

export const getIscedFields = () => request('/reference/isced-fields')

export const createCompany = (payload) =>
  request('/companies', { method: 'POST', body: JSON.stringify(payload) })

export const loginCompany = (email, password) =>
  request('/companies/login', { method: 'POST', body: JSON.stringify({ email, password }) })

export const loginAdmin = (email, password) =>
  request('/admin/login', { method: 'POST', body: JSON.stringify({ email, password }) })

export const extractCv = (talentId, cvText) =>
  request(`/candidates/${talentId}/extract-cv`, { method: 'POST', body: JSON.stringify({ cv_text: cvText }) })

export const submitCandidateSurvey = (talentId, values) =>
  request(`/candidates/${talentId}/survey`, { method: 'POST', body: JSON.stringify({ values }) })

export const getCandidateCompletion = (talentId) => request(`/candidates/${talentId}/completion`)

export const getCandidateSurveyValues = (talentId) => request(`/candidates/${talentId}/survey-values`)

export const getPremiumRequest = (talentId) => request(`/candidates/${talentId}/premium-request`)

export const createPremiumRequest = (talentId, plan) =>
  request(`/candidates/${talentId}/premium-request`, { method: 'POST', body: JSON.stringify({ plan }) })

export const createVacancy = (payload) =>
  request('/vacancies', { method: 'POST', body: JSON.stringify(payload) })

export const getVacancy = (vacancyId) => request(`/vacancies/${vacancyId}`)

export const extractVacancyDescription = (vacancyId, descriptionText) =>
  request(`/vacancies/${vacancyId}/extract-description`, {
    method: 'POST', body: JSON.stringify({ description_text: descriptionText }),
  })

export const submitVacancyWorkshop = (vacancyId, values) =>
  request(`/vacancies/${vacancyId}/workshop`, { method: 'POST', body: JSON.stringify({ values }) })

export const runMatch = (vacancyId, payload) =>
  request(`/vacancies/${vacancyId}/match`, { method: 'POST', body: JSON.stringify(payload) })

export const getMatchRun = (matchRunId) => request(`/matches/${matchRunId}`)

// --- Admin: Phase 1 reporting endpoints ---

export const getSignups = (granularity = 'day') =>
  request(`/admin/reports/signups?granularity=${granularity}`)

export const getCandidateActivity = (windowDays) =>
  request(`/admin/reports/candidate-activity${windowDays ? `?window_days=${windowDays}` : ''}`)

export const getSubscriptionBreakdown = () => request('/admin/reports/subscriptions')

export const getCandidateReport = (talentId) => request(`/admin/candidates/${talentId}/report`)

export const getCompanyReport = (companyId) => request(`/admin/companies/${companyId}/report`)

export const getIngestionHealth = () => request('/admin/reports/ingestion-health')

// --- Admin: manual/recurring process "Run now" tasks ---

export const getTaskStatus = () => request('/admin/tasks/status')

export const runTask = (taskName) => request(`/admin/tasks/${taskName}/run`, { method: 'POST' })

export const runAllReferenceRefresh = () =>
  request('/admin/tasks/reference-refresh/run-all', { method: 'POST' })

// --- Admin: Phase 2 review-queue endpoints ---

export const getDedupReview = () => request('/admin/dedup-review')

export const resolveDedupReview = (reviewId, decision, note) =>
  request(`/admin/dedup-review/${reviewId}/resolve`, { method: 'POST', body: JSON.stringify({ decision, note }) })

export const getSponsorReview = () => request('/admin/sponsor-review')

export const resolveSponsorReview = (vacancyId, decision, note) =>
  request(`/admin/sponsor-review/${vacancyId}/resolve`, { method: 'POST', body: JSON.stringify({ decision, note }) })

export const getExtractionReview = (limit = 50) => request(`/admin/extraction-review?limit=${limit}`)

export const getPremiumRequestQueue = () => request('/admin/premium-requests')

export const resolvePremiumRequest = (requestId, decision) =>
  request(`/admin/premium-requests/${requestId}/resolve`, { method: 'POST', body: JSON.stringify({ decision }) })

export { ApiError, BASE_URL }
