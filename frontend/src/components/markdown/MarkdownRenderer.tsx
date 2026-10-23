import "katex/dist/katex.min.css"
import "./code-theme.css"

import ReactMarkdown from "react-markdown"
import rehypeHighlight from "rehype-highlight"
import rehypeKatex from "rehype-katex"
import remarkGfm from "remark-gfm"
import remarkMath from "remark-math"

import { linkCitations } from "@/lib/citations"
import { normalizeMath } from "@/lib/math"
import { cn } from "@/lib/utils"

import { CodeBlock } from "./CodeBlock"

export interface CitationProps {
  /** Number of sources; [n] markers up to this count become clickable. */
  count: number
  /** Kind of source n, so document and web citations keep their own colours in one answer. */
  kindOf: (n: number) => "document" | "web"
  onCite: (n: number) => void
}

/** Heavy markdown pipeline (GFM, math, syntax highlighting). Loaded lazily; raw HTML is never rendered. */
export default function MarkdownRenderer({ content, citations }: { content: string; citations?: CitationProps }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[[rehypeHighlight, { detect: true }], rehypeKatex]}
      components={{
        pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
        a: ({ node: _node, href, children, ...props }) => {
          const cite = href?.startsWith("#cite-") ? Number(href.slice(6)) : null
          if (cite && citations) {
            return (
              <button
                type="button"
                onClick={() => citations.onCite(cite)}
                aria-label={`Show source ${cite}`}
                className={cn(
                  "mx-0.5 inline-flex h-[1.125rem] min-w-[1.125rem] -translate-y-px items-center justify-center rounded-md px-1 align-middle text-[0.6875rem] font-medium tabular-nums no-underline transition-colors",
                  citations.kindOf(cite) === "web"
                    ? "bg-step-route/10 text-step-route hover:bg-step-route/20"
                    : "bg-step-docs/10 text-step-docs hover:bg-step-docs/20",
                )}
              >
                {cite}
              </button>
            )
          }
          return (
            <a href={href} {...props} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          )
        },
        table: ({ node: _node, ...props }) => (
          <div className="table-wrap">
            <table {...props} />
          </div>
        ),
      }}
    >
      {linkCitations(normalizeMath(content), citations?.count ?? 0)}
    </ReactMarkdown>
  )
}
