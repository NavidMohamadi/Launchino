import { useState } from 'react'
import ReviewSection from './ReviewSection'
import ReportsSection from './ReportsSection'

const SECTIONS = {
  review: { label: 'Review', Component: ReviewSection },
  reports: { label: 'Reports', Component: ReportsSection },
}

export default function AdminDashboardPage() {
  const [section, setSection] = useState('review')
  const { Component } = SECTIONS[section]

  return (
    <div>
      <h1>Admin dashboard</h1>
      <div className="sub-nav">
        {Object.entries(SECTIONS).map(([key, { label }]) => (
          <button key={key} type="button" className={`tab${section === key ? ' active' : ''}`}
            onClick={() => setSection(key)}>
            {label}
          </button>
        ))}
      </div>
      <Component />
    </div>
  )
}
