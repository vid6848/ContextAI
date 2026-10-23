import { BookOpen, Check, Copy, FileText, Pencil, RotateCcw, ThumbsDown, ThumbsUp } from "lucide-react"
import { useMemo } from "react"
import { useState } from "react"
import { toast } from "sonner"

import { AgentTrace } from "@/components/AgentTrace"
import { Markdown } from "@/components/Markdown"
import { WebSourceStrip } from "@/components/Sources"
import { ToolCard } from "@/components/ToolCards"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { ChatMessage } from "@/lib/types"
import { cn } from "@/lib/utils"
import { useChat } from "@/store/chat"
import { useCitations } from "@/store/citations"

function ActionButton({
  label,
  onClick,
  pressed,
  children,
}: {
  label: string
  onClick: () => void
  pressed?: boolean
  children: React.ReactNode
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className={cn("size-8 text-muted-foreground", pressed && "text-foreground")}
          onClick={onClick}
          aria-label={label}
          aria-pressed={pressed}
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <ActionButton
      label={copied ? "Copied" : "Copy"}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        } catch {
          toast.error("Couldn't copy to the clipboard.")
        }
      }}
    >
      {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
    </ActionButton>
  )
}

export function UserMessage({ message }: { message: ChatMessage }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(message.content)
  const busy = useChat((s) => !!s.streaming)
  const edit = useChat((s) => s.edit)

  if (editing) {
    const submit = () => {
      if (!draft.trim()) return
      setEditing(false)
      edit(message.key, draft)
    }
    return (
      <div className="rounded-2xl border bg-card p-3 shadow-xs">
        <Textarea
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault()
              submit()
            }
            if (e.key === "Escape") setEditing(false)
          }}
          className="min-h-20 resize-none border-0 bg-transparent p-1 text-[1rem] shadow-none focus-visible:ring-0"
        />
        <div className="mt-2 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setEditing(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!draft.trim()}>
            Send
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="group flex flex-col items-end">
      {message.meta?.attachments?.length ? (
        <ul className="mb-1.5 flex max-w-[85%] flex-wrap justify-end gap-1.5" aria-label="Attached files">
          {message.meta.attachments.map((name) => (
            <li key={name} className="flex items-center gap-2 rounded-xl border bg-card py-1.5 pr-3 pl-2 text-[0.8125rem]">
              <span className="flex size-6 items-center justify-center rounded-md bg-step-docs/10 text-step-docs">
                <FileText className="size-3.5" />
              </span>
              <span className="max-w-[13rem] truncate">{name}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <div className="max-w-[85%] rounded-2xl rounded-br-md bg-secondary px-4 py-2.5 text-[1rem] leading-relaxed whitespace-pre-wrap">
        {message.content}
      </div>
      <div className="mt-1 flex opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100 max-md:opacity-100">
        <CopyButton text={message.content} />
        {!busy && (
          <ActionButton
            label="Edit"
            onClick={() => {
              setDraft(message.content)
              setEditing(true)
            }}
          >
            <Pencil className="size-4" />
          </ActionButton>
        )}
      </div>
    </div>
  )
}

export function AssistantMessage({ message, isLast }: { message: ChatMessage; isLast: boolean }) {
  const busy = useChat((s) => !!s.streaming)
  const regenerate = useChat((s) => s.regenerate)
  const setFeedback = useChat((s) => s.setFeedback)
  const feedback = message.meta?.feedback
  const rate = (rating: "up" | "down") =>
    setFeedback(message.key, feedback === rating ? null : rating)
      .then(() => feedback !== rating && toast("Thanks for the feedback"))
      .catch(() => toast.error("Couldn't save your feedback."))
  const waiting = !!message.streaming && !message.content
  const showSources = useCitations((s) => s.show)
  const metaSources = message.meta?.sources
  const sources = metaSources ?? []
  const sourceKind = sources[0]?.kind === "web" ? "web" : "document"
  // Only numbered sources (answers since citations shipped) get clickable [n] markers
  const citations = useMemo(() => {
    if (!metaSources?.length || metaSources[0].n == null) return undefined
    const kind = metaSources[0].kind === "web" ? ("web" as const) : ("document" as const)
    return { count: metaSources.length, kind, onCite: (n: number) => showSources(message.key, n) }
  }, [metaSources, showSources, message.key])

  return (
    <div className="group">
      <AgentTrace meta={message.meta} streaming={waiting} />
      <ToolCard tool={message.meta?.tool_used} output={message.meta?.tool_output} />
      {sourceKind === "web" && sources.length > 0 && <WebSourceStrip sources={sources} messageKey={message.key} />}
      {message.content && <Markdown content={message.content} streaming={message.streaming} citations={citations} />}

      {message.meta?.stopped && <p className="mt-2 text-sm text-muted-foreground">You stopped this answer.</p>}
      {message.error && (
        <p role="alert" className="mt-2 rounded-lg border border-step-error/30 bg-step-error/5 px-3 py-2 text-sm text-step-error">
          {message.error}
        </p>
      )}

      {!message.streaming && (
        <div className={cn("mt-1.5 -ml-2 flex", !isLast && "opacity-0 transition-opacity group-hover:opacity-100 max-md:opacity-100")}>
          {message.content && <CopyButton text={message.content} />}
          {message.id != null && message.content && !message.error && (
            <>
              <ActionButton label="Good response" pressed={feedback === "up"} onClick={() => rate("up")}>
                <ThumbsUp className={cn("size-4", feedback === "up" && "fill-current")} />
              </ActionButton>
              <ActionButton label="Bad response" pressed={feedback === "down"} onClick={() => rate("down")}>
                <ThumbsDown className={cn("size-4", feedback === "down" && "fill-current")} />
              </ActionButton>
            </>
          )}
          {citations && (
            <Button
              variant="ghost"
              size="sm"
              className="h-8 gap-1.5 px-2 text-muted-foreground"
              onClick={() => showSources(message.key, 1)}
            >
              <BookOpen className="size-4" />
              {sources.length} {sources.length === 1 ? "source" : "sources"}
            </Button>
          )}
          {isLast && !busy && (
            <ActionButton label={message.error ? "Retry" : "Regenerate"} onClick={() => regenerate(message.key)}>
              <RotateCcw className="size-4" />
            </ActionButton>
          )}
        </div>
      )}
    </div>
  )
}
