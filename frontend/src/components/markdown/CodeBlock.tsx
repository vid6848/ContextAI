import { Check, Copy } from "lucide-react"
import { isValidElement, useRef, useState, type ReactNode } from "react"

/** Fenced code: language label and a copy button over a highlighted block. */
export function CodeBlock({ children }: { children?: ReactNode }) {
  const codeRef = useRef<HTMLDivElement>(null)
  const [copied, setCopied] = useState(false)

  const className = isValidElement<{ className?: string }>(children) ? children.props.className ?? "" : ""
  const language = /language-([\w+#-]+)/.exec(className)?.[1]

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(codeRef.current?.textContent ?? "")
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard unavailable */
    }
  }

  return (
    <div className="code-block not-prose">
      <div className="flex items-center justify-between border-b px-3 py-1.5 text-xs text-muted-foreground">
        <span className="font-mono">{language ?? "text"}</span>
        <button
          type="button"
          onClick={copy}
          className="inline-flex items-center gap-1.5 rounded px-1.5 py-0.5 hover:bg-accent hover:text-foreground touch:-my-1 touch:px-2.5 touch:py-2"
        >
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <div ref={codeRef}>
        <pre>{children}</pre>
      </div>
    </div>
  )
}
