import { useCallback, useEffect, useLayoutEffect, useRef } from "react"

/**
 * Keep a scroll container pinned to the bottom while content grows (streaming), but stop following as
 * soon as the reader scrolls up, and resume when they scroll back down. `trigger` should change whenever
 * the content does.
 */
export function useStickToBottom<T extends HTMLElement>(trigger: unknown) {
  const ref = useRef<T>(null)
  const stick = useRef(true)

  const onScroll = useCallback(() => {
    const el = ref.current
    if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  }, [])

  const scrollToBottom = useCallback(() => {
    const el = ref.current
    if (el) el.scrollTop = el.scrollHeight
    stick.current = true
  }, [])

  useLayoutEffect(() => {
    if (stick.current) scrollToBottom()
  }, [trigger, scrollToBottom])

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.addEventListener("scroll", onScroll, { passive: true })
    return () => el.removeEventListener("scroll", onScroll)
  }, [onScroll])

  return { ref, scrollToBottom }
}
