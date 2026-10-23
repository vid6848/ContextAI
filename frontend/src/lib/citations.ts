/**
 * Turn [n] citation markers into markdown links (#cite-n) that the renderer shows as clickable pills.
 * Only numbers that match a source are linked; code, existing links and footnote-style refs are left alone.
 */
export function linkCitations(markdown: string, sourceCount: number): string {
  if (!sourceCount) return markdown
  return markdown
    .split(/(```[\s\S]*?```|`[^`\n]*`)/g)
    .map((part, i) =>
      i % 2 === 1
        ? part
        : part.replace(/\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\](?![(:])/g, (match, nums: string) => {
            // [2] and grouped forms like [1, 3]
            const ns = nums.split(",").map((x) => Number(x.trim()))
            return ns.every((n) => n >= 1 && n <= sourceCount) ? ns.map((n) => `[${n}](#cite-${n})`).join("") : match
          }),
    )
    .join("")
}

export function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "")
  } catch {
    return url
  }
}
