import { memo } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { cn } from "@/lib/utils"

/** Renders assistant markdown. Raw HTML is not rendered (react-markdown's default), so output is XSS-safe. */
export const Markdown = memo(function Markdown({ content, streaming }: { content: string; streaming?: boolean }) {
  return (
    <div className={cn("md", streaming && "is-streaming")}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer noopener" />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
})
