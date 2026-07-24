import { useState } from 'react'
import OverviewTab from './OverviewTab'
import CandidateLookupTab from './CandidateLookupTab'
import CompanyLookupTab from './CompanyLookupTab'

const TABS = {
  overview: { label: 'Overview', Component: OverviewTab },
  candidate: { label: 'Candidate lookup', Component: CandidateLookupTab },
  company: { label: 'Company lookup', Component: CompanyLookupTab },
}

export default function ReportsSection() {
  const [tab, setTab] = useState('overview')
  const { Component } = TABS[tab]

  return (
    <div>
      <div className="sub-nav">
        {Object.entries(TABS).map(([key, { label }]) => (
          <button key={key} type="button" className={`tab${tab === key ? ' active' : ''}`}
            onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>
      <Component />
    </div>
  )
}
