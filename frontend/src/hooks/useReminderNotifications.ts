import { useEffect } from "react"
import { toast } from "sonner"

import { api } from "@/lib/api"
import type { Reminder } from "@/lib/types"

const POLL_MS = 30_000

function notify(r: Reminder) {
  toast(r.reminder_text, {
    description: "Reminder",
    duration: 15_000,
    action: { label: "Mark done", onClick: () => void api.completeReminder(r.id) },
  })
  if ("Notification" in window && Notification.permission === "granted" && document.visibilityState !== "visible") {
    new Notification("ContextAI reminder", { body: r.reminder_text, tag: `reminder-${r.id}` })
  }
}

/** Polls for reminders that have come due and alerts once per reminder (in-app toast + system notification). */
export function useReminderNotifications() {
  useEffect(() => {
    let stopped = false
    const check = async () => {
      try {
        for (const r of await api.dueReminders()) {
          if (stopped) return
          notify(r)
          await api.markNotified(r.id)
        }
      } catch {
        /* offline or server down: try again next tick */
      }
    }
    void check()
    const timer = setInterval(check, POLL_MS)
    const onFocus = () => void check()
    window.addEventListener("focus", onFocus)
    return () => {
      stopped = true
      clearInterval(timer)
      window.removeEventListener("focus", onFocus)
    }
  }, [])
}
