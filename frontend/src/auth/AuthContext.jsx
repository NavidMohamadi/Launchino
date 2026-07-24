import { createContext, useContext, useState } from 'react'
import { setAuthToken } from '../api'

const AuthContext = createContext(null)
const STORAGE_KEY = 'shexon_auth'

function loadStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(loadStored)

  // Synchronous, not in useEffect: must run before any child's mount-time API
  // call, and effects fire child-first (bottom-up), so a useEffect here could
  // lose that race on first paint.
  setAuthToken(auth?.token || null)

  const login = (role, token, profile) => {
    const next = { role, token, profile }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    setAuth(next)
  }

  const logout = () => {
    localStorage.removeItem(STORAGE_KEY)
    setAuth(null)
  }

  return <AuthContext.Provider value={{ auth, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
