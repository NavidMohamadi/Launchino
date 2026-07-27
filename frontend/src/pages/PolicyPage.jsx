import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Link } from 'react-router-dom'

export default function PolicyPage({ title, content }) {
  return (
    <div className="policy-page">
      <p><Link to="/login">&larr; Back to log in</Link></p>
      <h1>{title}</h1>
      <div className="card policy-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
    </div>
  )
}
