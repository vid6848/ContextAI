import { describe, expect, it } from "vitest"

import { normalizeMath } from "./math"

describe("normalizeMath", () => {
  it("converts \\( \\) to inline math", () => {
    expect(normalizeMath("Area is \\(\\pi r^2\\).")).toBe("Area is $\\pi r^2$.")
  })

  it("converts \\[ \\] to display math on its own lines", () => {
    expect(normalizeMath("So \\[ x = 1 \\] done")).toBe("So \n$$\nx = 1\n$$\n done")
  })

  it("promotes a line holding only $$…$$ to a display block", () => {
    expect(normalizeMath("Formula:\n$$x = \\frac{-b}{2a}$$\nDone")).toBe("Formula:\n$$\nx = \\frac{-b}{2a}\n$$\nDone")
  })

  it("escapes currency but keeps inline math", () => {
    expect(normalizeMath("BTC is $81,605, ETH $2,405; solve $ax^2 + bx + c = 0$.")).toBe(
      "BTC is \\$81,605, ETH \\$2,405; solve $ax^2 + bx + c = 0$.",
    )
  })

  it("leaves code alone", () => {
    const text = "Use `$5` or\n```\n\\[y\\] costs $3\n```"
    expect(normalizeMath(text)).toBe(text)
  })
})
