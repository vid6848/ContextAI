import type { Conversation } from "./types"

export type GroupLabel = "Today" | "Yesterday" | "Previous 7 days" | "Previous 30 days" | "Older"

const ORDER: GroupLabel[] = ["Today", "Yesterday", "Previous 7 days", "Previous 30 days", "Older"]

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

/** Bucket conversations by last activity, newest first, the way ChatGPT/Claude sidebars do. */
export function groupConversations(
  conversations: Conversation[],
  now: Date = new Date(),
): { label: GroupLabel; items: Conversation[] }[] {
  const today = startOfDay(now)
  const day = 86_400_000
  const buckets = new Map<GroupLabel, Conversation[]>()

  const sorted = [...conversations].sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  for (const c of sorted) {
    const t = startOfDay(new Date(c.updated_at))
    const label: GroupLabel =
      t >= today ? "Today"
        : t >= today - day ? "Yesterday"
          : t >= today - 7 * day ? "Previous 7 days"
            : t >= today - 30 * day ? "Previous 30 days"
              : "Older"
    if (!buckets.has(label)) buckets.set(label, [])
    buckets.get(label)!.push(c)
  }
  return ORDER.filter((l) => buckets.has(l)).map((label) => ({ label, items: buckets.get(label)! }))
}

export function formatDuration(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}
