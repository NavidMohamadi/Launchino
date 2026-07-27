import PolicyPage from './PolicyPage'
import content from '../content/privacy-policy.md?raw'

export default function PrivacyPolicyPage() {
  return <PolicyPage title="Privacy Policy" content={content} />
}
