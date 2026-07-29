// Single source of truth for the 5 per-category survey routes, so the
// dashboard's links, App.jsx's routes, and CategorySurveyPage's own parsing
// of the URL all agree -- one copy, not three independently hardcoded ones.
export const CATEGORY_SLUGS = {
  PRACT: 'practical-fit',
  TEAM: 'how-you-work',
  CAREER: 'where-youre-headed',
  MOT: 'what-drives-you',
  ENV: 'your-ideal-environment',
}

export const SLUG_TO_CATEGORY = Object.fromEntries(
  Object.entries(CATEGORY_SLUGS).map(([category, slug]) => [slug, category]),
)

export const surveyPathFor = (category) => `/candidate/survey/${CATEGORY_SLUGS[category]}`
