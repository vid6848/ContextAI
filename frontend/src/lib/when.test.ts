import { describe, expect, it } from "vitest"

import { formatWhen } from "./when"

describe("formatWhen", () => {
  const now = new Date(2026, 9, 23, 15, 30)
  it("uses Today / Tomorrow / Yesterday when close", () => {
    expect(formatWhen(new Date(2026, 9, 23, 20, 0).toISOString(), now)).toMatch(/^Today, /)
    expect(formatWhen(new Date(2026, 9, 24, 17, 0).toISOString(), now)).toMatch(/^Tomorrow, /)
    expect(formatWhen(new Date(2026, 9, 22, 9, 0).toISOString(), now)).toMatch(/^Yesterday, /)
  })
  it("adds the year only when it differs", () => {
    expect(formatWhen(new Date(2027, 0, 5, 9, 0).toISOString(), now)).toMatch(/2027/)
    expect(formatWhen(new Date(2026, 11, 5, 9, 0).toISOString(), now)).not.toMatch(/2026/)
  })
})
