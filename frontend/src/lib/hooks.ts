import { useCallback, useEffect, useState } from 'react'

export function useLoad<T>(loader: () => Promise<T>, dependencies: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<unknown>(null)

  const reload = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await loader()
      setData(result)
      return result
    } catch (caught) {
      setError(caught)
      throw caught
    } finally {
      setLoading(false)
    }
    // loader should be stable or dependencies should explicitly describe it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, dependencies)

  useEffect(() => {
    reload().catch(() => undefined)
  }, [reload])

  return { data, setData, loading, error, reload }
}
