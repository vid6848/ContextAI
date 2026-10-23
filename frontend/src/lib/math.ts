/**
 * Prepare LLM output for remark-math.
 *
 * - `\( … \)` and `\[ … \]` (common in model output) become `$…$` and block `$$`.
 * - A line holding only `$$…$$` becomes a display block instead of tiny inline math.
 * - A `$` directly followed by a digit is treated as currency and escaped, so "$81,605 and $1.6T"
 *   stays text while `$ax^2 + bx + c$` still renders.
 * Fenced and inline code are left untouched.
 */
export function normalizeMath(markdown: string): string {
  return markdown
    .split(/(```[\s\S]*?```|`[^`\n]*`)/g)
    .map((part, i) => {
      if (i % 2 === 1) return part
      return part
        .replace(/\\\[([\s\S]+?)\\\]/g, (_, expr: string) => `\n$$\n${expr.trim()}\n$$\n`)
        .replace(/\\\((.+?)\\\)/g, (_, expr: string) => `$${expr.trim()}$`)
        .replace(/^[ \t]*\$\$([^\n]+?)\$\$[ \t]*$/gm, (_, expr: string) => `$$\n${expr.trim()}\n$$`)
        .replace(/(?<![\\$])\$(?=\d)/g, "\\$")
    })
    .join("")
}
