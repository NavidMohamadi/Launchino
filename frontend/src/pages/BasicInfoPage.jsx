import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import * as api from '../api'
import { useAuth } from '../auth/AuthContext'
import { TextField, Select } from '../components/formFields'

const CONTACT_PREFERENCES = ['email', 'phone', 'either']

export default function BasicInfoPage() {
  const { auth } = useAuth()
  const talentId = auth.profile.talent_id
  const navigate = useNavigate()

  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [contactPreference, setContactPreference] = useState('email')

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  useEffect(() => {
    api.getCandidate(talentId)
      .then((candidate) => {
        setFullName(candidate.full_name || '')
        setEmail(candidate.email || '')
        setPhone(candidate.phone || '')
        setContactPreference(candidate.contact_preference || 'email')
      })
      .catch((err) => setLoadError(err.message))
      .finally(() => setLoading(false))
  }, [talentId])

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    setSubmitError(null)
    try {
      await api.updateBasicInfo(talentId, {
        phone: phone.trim() || null, contact_preference: contactPreference,
      })
      navigate('/candidate')
    } catch (err) {
      setSubmitError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (loadError) return <p className="hint-error">Could not load your account details: {loadError}</p>
  if (loading) return <p>Loading...</p>

  return (
    <div>
      <p style={{ marginBottom: 16 }}>
        <Link to="/candidate">&larr; Back to your profile</Link>
      </p>
      <h1>Basic Info</h1>
      <div className="card">
        <div className="field-group" style={{ marginBottom: 16 }}>
          <div className="field">
            <span>Name</span>
            <p style={{ margin: '4px 0 0' }}>{fullName}</p>
          </div>
          <div className="field">
            <span>Email</span>
            <p style={{ margin: '4px 0 0' }}>{email}</p>
          </div>
        </div>
        <p style={{ fontSize: 13, color: 'var(--ll-neutral-600)', marginBottom: 12 }}>
          How companies can reach you. This is never compared against a vacancy -- it's just your contact details.
        </p>
        <form onSubmit={handleSubmit}>
          <div className="field-group">
            <TextField
              label="Phone" value={phone} onChange={setPhone} placeholder="+31 6 1234 5678"
              required={contactPreference === 'phone'}
            />
            <Select label="How should companies contact you?" value={contactPreference} options={CONTACT_PREFERENCES} onChange={setContactPreference} />
          </div>
          <div style={{ marginTop: 20 }}>
            <button type="submit" disabled={submitting}>{submitting ? 'Saving…' : 'Save'}</button>
          </div>
          {submitError && <p className="hint-error">{submitError}</p>}
        </form>
      </div>
    </div>
  )
}
