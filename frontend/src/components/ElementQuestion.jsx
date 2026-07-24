import TriStateAnswer from './TriStateAnswer'
import { getValueEditor } from './valueEditors'

// One Fit Dictionary element, rendered for either side. Combines the shared
// tri-state wrapper with whichever value editor matches this element's
// comparator_key (a closed set of 9 -- see valueEditors/index.jsx).
export default function ElementQuestion({ element, side, answer, onChange }) {
  const ValueEditor = getValueEditor(element.comparator_key, side)
  const question = side === 'candidate' ? element.candidate_question : element.vacancy_question

  return (
    <div className="element-question">
      <div className="element-question-header">
        <span className="element-id">{element.element_id}</span>
        <p className="question-text">{question}</p>
      </div>
      <TriStateAnswer side={side} answer={answer} onChange={onChange}>
        {ValueEditor ? (
          <ValueEditor value={answer.value || {}} onChange={(value) => onChange({ ...answer, value })} />
        ) : (
          <p className="hint-warning">No editor registered for comparator_key "{element.comparator_key}".</p>
        )}
      </TriStateAnswer>
    </div>
  )
}
