import { describe, expect, it } from "vitest"

import { domainOf, linkCitations } from "./citations"

describe("linkCitations", () => {
  it("links markers that match a source, including adjacent ones", () => {
    expect(linkCitations("Revenue grew 18% [1][2].", 2)).toBe("Revenue grew 18% [1](#cite-1)[2](#cite-2).")
  })

  it("ignores numbers without a source, links, refs and code", () => {
    const text = "See [3] and [a link](x) and [1](http://e.com) and [1]: def and `arr[1]`"
    expect(linkCitations(text, 2)).toBe(text)
  })

  it("is a no-op without sources", () => {
    expect(linkCitations("[1]", 0)).toBe("[1]")
  })
})

describe("domainOf", () => {
  it("strips www and falls back to the input", () => {
    expect(domainOf("https://www.python.org/downloads/")).toBe("python.org")
    expect(domainOf("not a url")).toBe("not a url")
  })
})
