import PolicyPage from './PolicyPage'
import content from '../content/terms-of-service.md?raw'

export default function TermsOfServicePage() {
  return <PolicyPage title="Terms of Service" content={content} />
}
