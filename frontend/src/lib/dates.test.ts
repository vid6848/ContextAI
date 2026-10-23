import { describe, expect, it } from "vitest"

import { formatDuration, groupConversations } from "./dates"

const conv = (id: string, updated_at: string) => ({ id, title: id, created_at: updated_at, updated_at })

describe("groupConversations", () => {
  it("buckets by last activity, newest first, skipping empty groups", () => {
    const now = new Date("2026-10-23T15:00:00")
    const groups = groupConversations(
      [
        conv("old", "2026-01-02T10:00:00"),
        conv("today-early", "2026-10-23T08:00:00"),
        conv("yesterday", "2026-10-22T23:00:00"),
        conv("today-late", "2026-10-23T14:00:00"),
        conv("last-week", "2026-10-18T12:00:00"),
      ],
      now,
    )
    expect(groups.map((g) => [g.label, g.items.map((c) => c.id)])).toEqual([
      ["Today", ["today-late", "today-early"]],
      ["Yesterday", ["yesterday"]],
      ["Previous 7 days", ["last-week"]],
      ["Older", ["old"]],
    ])
  })
})

describe("formatDuration", () => {
  it("uses ms below a second and one decimal above", () => {
    expect(formatDuration(349)).toBe("349ms")
    expect(formatDuration(1234)).toBe("1.2s")
  })
})
