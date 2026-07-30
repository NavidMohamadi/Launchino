// Single source of truth for the per-category survey routes, so the
// dashboard's links, App.jsx's routes, and CategorySurveyPage's own parsing
// of the URL all agree -- one copy, not three independently hardcoded ones.
// EDU/CAP/TASK route to their own dedicated page components (App.jsx), not
// the generic CategorySurveyPage -- their repeatable-entry values don't fit
// that page's single-value editor model (see PROJECT_NOTES.md's Phase 4
// entry) -- but still live under this same slug scheme so surveyPathFor and
// the dashboard's card-click wiring work identically for every category.
export const CATEGORY_SLUGS = {
  EDU: 'education',
  PRACT: 'practical-fit',
  TEAM: 'how-you-work',
  CAREER: 'where-youre-headed',
  MOT: 'what-drives-you',
  ENV: 'your-ideal-environment',
  CAP: 'capabilities',
  TASK: 'task-history',
}

export const SLUG_TO_CATEGORY = Object.fromEntries(
  Object.entries(CATEGORY_SLUGS).map(([category, slug]) => [slug, category]),
)

export const surveyPathFor = (category) => `/candidate/survey/${CATEGORY_SLUGS[category]}`

// Basic Info isn't a Fit Dictionary category (see PROJECT_NOTES.md's Phase
// 1/4 entries) -- plain talent columns, its own page, not part of the
// category slug map above.
export const BASIC_INFO_PATH = '/candidate/survey/basic-info'
