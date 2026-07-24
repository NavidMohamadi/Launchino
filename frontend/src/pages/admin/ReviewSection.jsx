import { useState } from 'react'
import DedupReviewTab from './DedupReviewTab'
import SponsorReviewTab from './SponsorReviewTab'
import ExtractionReviewTab from './ExtractionReviewTab'

const TABS = {
  dedup: { label: 'Duplicate review', Component: DedupReviewTab },
  sponsor: { label: 'Sponsor review', Component: SponsorReviewTab },
  extraction: { label: 'Extraction spot-check', Component: ExtractionReviewTab },
}

export default function ReviewSection() {
  const [tab, setTab] = useState('dedup')
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
      <div className="card">
        <Component />
      </div>
    </div>
  )
}
