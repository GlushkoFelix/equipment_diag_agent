import { useEffect, useState } from 'react'

export function useCountdown(expiresAt: string | null | undefined) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!expiresAt) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [expiresAt])

  if (!expiresAt) return { seconds: 0, expired: true }
  const seconds = Math.max(0, Math.floor((new Date(expiresAt).getTime() - now) / 1000))
  return { seconds, expired: seconds <= 0 }
}
