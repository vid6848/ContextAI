import "katex/dist/katex.min.css"
import "./code-theme.css"

import ReactMarkdown from "react-markdown"
import rehypeHighlight from "rehype-highlight"
import rehypeKatex from "rehype-katex"
import remarkGfm from "remark-gfm"
import remarkMath from "remark-math"

import { normalizeMath } from "@/lib/math"

import { CodeBlock } from "./CodeBlock"

/** Heavy markdown pipeline (GFM, math, syntax highlighting). Loaded lazily; raw HTML is never rendered. */
export default function MarkdownRenderer({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }], rehypeKatex]}
      components={{
        pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
        a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer noopener" />,
        table: ({ node: _node, ...props }) => (
          <div className="table-wrap">
            <table {...props} />
          </div>
        ),
      }}
    >
      {normalizeMath(content)}
    </ReactMarkdown>
  )
}
