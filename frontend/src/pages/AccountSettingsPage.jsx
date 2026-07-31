import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import * as api from '../api'
import { useAuth } from '../auth/AuthContext'
import { TextField, Select } from '../components/formFields'

const CONTACT_PREFERENCES = ['email', 'phone', 'either']
const DELETE_CONFIRMATION_WORD = 'DELETE'

// Formerly "Basic Info" -- renamed since it now also holds account deletion,
// not just contact fields. Deliberately reachable at any time (its own
// route, not part of the /survey/ sequence) and never part of the
// dashboard's "Continue: ..." CTA -- see PROJECT_NOTES.md's stuck-CTA fix
// entry for why that matters.
export default function AccountSettingsPage() {
  const { auth, logout } = useAuth()
  const talentId = auth.profile.talent_id

  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [contactPreference, setContactPreference] = useState('email')

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)
  const [saved, setSaved] = useState(false)

  const [deleteStage, setDeleteStage] = useState('idle') // idle -> confirming
  const [confirmText, setConfirmText] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState(null)

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
    setSaved(false)
    try {
      await api.updateBasicInfo(talentId, {
        phone: phone.trim() || null, contact_preference: contactPreference,
      })
      setSaved(true)
    } catch (err) {
      setSubmitError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete() {
    setDeleting(true)
    setDeleteError(null)
    try {
      await api.deleteCandidate(talentId)
      // Logs out and lets RequireRole's own redirect take it from there --
      // same mechanism the "Log out" link already uses, not a second one.
      logout()
    } catch (err) {
      setDeleteError(err.message)
      setDeleting(false)
    }
  }

  if (loadError) return <p className="hint-error">Could not load your account details: {loadError}</p>
  if (loading) return <p>Loading...</p>

  return (
    <div>
      <p style={{ marginBottom: 16 }}>
        <Link to="/candidate">&larr; Back to your profile</Link>
      </p>
      <h1>Account Settings</h1>
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
          {saved && !submitError && <p className="hint-success">Saved.</p>}
          {submitError && <p className="hint-error">{submitError}</p>}
        </form>
      </div>

      <div className="card" style={{ marginTop: 24, border: '1px solid #B01818' }}>
        <h2 style={{ color: '#B01818', marginTop: 0 }}>Danger zone</h2>
        <p style={{ fontSize: 13, color: 'var(--ll-neutral-600)' }}>
          Deleting your account is permanent. Your name and email are anonymized, your survey answers are
          permanently deleted, and you won't be able to log back in. This cannot be undone.
        </p>

        {deleteStage === 'idle' && (
          <button type="button" className="secondary reject" onClick={() => setDeleteStage('confirming')}>
            Delete my account
          </button>
        )}

        {deleteStage === 'confirming' && (
          <div>
            <TextField
              label={`Type ${DELETE_CONFIRMATION_WORD} to confirm`} value={confirmText} onChange={setConfirmText}
              placeholder={DELETE_CONFIRMATION_WORD}
            />
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button
                type="button" className="secondary reject"
                disabled={confirmText.trim() !== DELETE_CONFIRMATION_WORD || deleting}
                onClick={handleDelete}
              >
                {deleting ? 'Deleting…' : 'Permanently delete my account'}
              </button>
              <button type="button" className="secondary" disabled={deleting} onClick={() => { setDeleteStage('idle'); setConfirmText(''); setDeleteError(null) }}>
                Cancel
              </button>
            </div>
            {deleteError && <p className="hint-error">{deleteError}</p>}
          </div>
        )}
      </div>
    </div>
  )
}
