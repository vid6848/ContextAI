import { useSyncExternalStore } from "react"

/** Live result of a CSS media query, e.g. useMediaQuery("(max-width: 639px)"). */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mql = window.matchMedia(query)
      mql.addEventListener("change", onChange)
      return () => mql.removeEventListener("change", onChange)
    },
    () => window.matchMedia(query).matches,
    () => false,
  )
}

/** True on touch-first devices (phones, tablets), where focusing an input pops up the on-screen keyboard. */
export const isTouchDevice = () => typeof window !== "undefined" && window.matchMedia("(hover: none)").matches
