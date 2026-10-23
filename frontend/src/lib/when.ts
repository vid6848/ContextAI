/** "Tomorrow, 5:00 PM", "Today, 8:30 PM", "Fri 30 Oct, 9:00 AM" in the user's locale. */
export function formatWhen(iso: string, now: Date = new Date()): string {
  const d = new Date(iso)
  const time = d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const diffDays = Math.round((day(d) - day(now)) / 86_400_000)
  if (diffDays === 0) return `Today, ${time}`
  if (diffDays === 1) return `Tomorrow, ${time}`
  if (diffDays === -1) return `Yesterday, ${time}`
  const sameYear = d.getFullYear() === now.getFullYear()
  const date = d.toLocaleDateString(undefined, {
    weekday: Math.abs(diffDays) < 7 ? "short" : undefined,
    day: "numeric",
    month: "short",
    year: sameYear ? undefined : "numeric",
  })
  return `${date}, ${time}`
}
