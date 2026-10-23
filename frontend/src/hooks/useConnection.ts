import { useEffect, useState } from "react"

export type ConnectionState = "online" | "offline" | "server-down"

/**
 * Browser connectivity plus a health check of the API, so the UI can say whether the network or the
 * server is the problem. Re-checks every 5 s while something is wrong, and every 60 s otherwise.
 */
export function useConnection(): ConnectionState {
  const [state, setState] = useState<ConnectionState>(() => (navigator.onLine ? "online" : "offline"))

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>
    let cancelled = false

    const check = async () => {
      let next: ConnectionState
      if (!navigator.onLine) next = "offline"
      else {
        try {
          const resp = await fetch("/health", { cache: "no-store" })
          next = resp.ok ? "online" : "server-down"
        } catch {
          next = "server-down"
        }
      }
      if (cancelled) return
      setState(next)
      timer = setTimeout(check, next === "online" ? 60_000 : 5_000)
    }

    const recheck = () => {
      clearTimeout(timer)
      void check()
    }
    void check()
    window.addEventListener("online", recheck)
    window.addEventListener("offline", recheck)
    return () => {
      cancelled = true
      clearTimeout(timer)
      window.removeEventListener("online", recheck)
      window.removeEventListener("offline", recheck)
    }
  }, [])

  return state
}
