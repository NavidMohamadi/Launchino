import { useEffect, useState } from 'react'
import { getFitDictionary } from '../api'

// Fetches GET /fit-dictionary with the current selections and re-fetches
// whenever they change -- activation is resolved by the backend's
// activation.is_activated (src/activation.py), never re-implemented here.
export function useFitDictionary({ candidateSelectedIds = [], vacancyActivatedIds = [] } = {}) {
  const [elements, setElements] = useState(null)
  const [error, setError] = useState(null)
  const key = `${candidateSelectedIds.join(',')}|${vacancyActivatedIds.join(',')}`

  useEffect(() => {
    let cancelled = false
    getFitDictionary({ candidateSelectedIds, vacancyActivatedIds })
      .then((data) => { if (!cancelled) setElements(data) })
      .catch((err) => { if (!cancelled) setError(err.message) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  return { elements, error, loading: elements === null && !error }
}
