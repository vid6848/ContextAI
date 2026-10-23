import { lazy, memo, Suspense } from "react"

import { cn } from "@/lib/utils"

// The markdown/highlighting/math pipeline is the heaviest part of the bundle; load it on first use.
const MarkdownRenderer = lazy(() => import("./markdown/MarkdownRenderer"))

export const Markdown = memo(function Markdown({ content, streaming }: { content: string; streaming?: boolean }) {
  return (
    <div className={cn("md", streaming && "is-streaming")}>
      <Suspense fallback={<p className="whitespace-pre-wrap">{content}</p>}>
        <MarkdownRenderer content={content} />
      </Suspense>
    </div>
  )
})
