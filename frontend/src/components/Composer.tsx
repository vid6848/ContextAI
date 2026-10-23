import { ArrowUp, FileText, LoaderCircle, Paperclip, Square, TriangleAlert, X } from "lucide-react"
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { MAX_UPLOAD_MB, uploadWithProgress } from "@/lib/api"
import { cn } from "@/lib/utils"

const MAX_ATTACHMENTS = 5

interface Attachment {
  id: string
  name: string
  status: "uploading" | "ready" | "error"
  progress: number
  detail?: string
  controller: AbortController
}

export interface ComposerHandle {
  focus: () => void
  addFiles: (files: FileList | File[]) => void
}

interface ComposerProps {
  streaming: boolean
  onSend: (text: string, attachments: string[]) => void
  onStop: () => void
}

export const Composer = forwardRef<ComposerHandle, ComposerProps>(function Composer({ streaming, onSend, onStop }, ref) {
  const [value, setValue] = useState("")
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const textarea = useRef<HTMLTextAreaElement>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  const update = (id: string, patch: Partial<Attachment>) =>
    setAttachments((list) => list.map((a) => (a.id === id ? { ...a, ...patch } : a)))

  const addFiles = (files: FileList | File[]) => {
    const pdfs = Array.from(files).filter((f) => {
      if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) {
        toast.error(`${f.name} isn't a PDF. Only PDFs can be attached.`)
        return false
      }
      if (f.size > MAX_UPLOAD_MB * 1024 * 1024) {
        toast.error(`${f.name} is larger than ${MAX_UPLOAD_MB} MB.`)
        return false
      }
      return true
    })
    const room = MAX_ATTACHMENTS - attachments.length
    if (pdfs.length > room) toast.error(`You can attach up to ${MAX_ATTACHMENTS} files per message.`)

    for (const file of pdfs.slice(0, Math.max(room, 0))) {
      const att: Attachment = {
        id: crypto.randomUUID(),
        name: file.name,
        status: "uploading",
        progress: 0,
        controller: new AbortController(),
      }
      setAttachments((list) => [...list, att])
      uploadWithProgress(file, (p) => update(att.id, { progress: p }), att.controller.signal)
        .then((res) =>
          update(att.id, { status: "ready", progress: 1, name: res.document_name, detail: `${res.total_pages} pages` }),
        )
        .catch((err: Error) => {
          if (err.name === "AbortError") return
          update(att.id, { status: "error", detail: err.message })
        })
    }
    textarea.current?.focus()
  }

  const removeAttachment = (att: Attachment) => {
    att.controller.abort()
    setAttachments((list) => list.filter((a) => a.id !== att.id))
  }

  useImperativeHandle(ref, () => ({ focus: () => textarea.current?.focus(), addFiles }))

  // Grow with the content up to ~8 lines, then scroll
  useEffect(() => {
    const el = textarea.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, parseFloat(getComputedStyle(el).maxHeight) || 240)}px`
  }, [value])

  const uploading = attachments.some((a) => a.status === "uploading")
  const ready = attachments.filter((a) => a.status === "ready")
  const canSend = !streaming && !uploading && (value.trim().length > 0 || ready.length > 0)

  const submit = () => {
    if (!canSend) return
    const text = value.trim() || (ready.length === 1 ? "Summarize this document." : "Summarize these documents.")
    onSend(text, ready.map((a) => a.name))
    setValue("")
    setAttachments([])
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (streaming) onStop()
        else submit()
      }}
      className="rounded-3xl border bg-card p-2 shadow-[0_1px_2px_rgb(0_0_0/0.04),0_4px_16px_-6px_rgb(0_0_0/0.08)] focus-within:border-ring/60"
    >
      {attachments.length > 0 && (
        <ul className="flex flex-wrap gap-2 px-1 pt-1 pb-2" aria-label="Attached files">
          {attachments.map((a) => (
            <li
              key={a.id}
              className={cn(
                "relative flex max-w-[15rem] items-center gap-2.5 overflow-hidden rounded-xl border bg-background py-2 pr-8 pl-2.5",
                a.status === "error" && "border-step-error/40",
              )}
            >
              <span
                className={cn(
                  "flex size-8 shrink-0 items-center justify-center rounded-lg",
                  a.status === "error" ? "bg-step-error/10 text-step-error" : "bg-step-docs/10 text-step-docs",
                )}
              >
                {a.status === "uploading" ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : a.status === "error" ? (
                  <TriangleAlert className="size-4" />
                ) : (
                  <FileText className="size-4" />
                )}
              </span>
              <span className="min-w-0">
                <span className="block truncate text-[0.8125rem] font-medium">{a.name}</span>
                <span className={cn("block truncate text-xs text-muted-foreground", a.status === "error" && "text-step-error")}>
                  {a.status === "uploading"
                    ? a.progress < 1
                      ? `Uploading ${Math.round(a.progress * 100)}%`
                      : "Reading the PDF…"
                    : a.detail}
                </span>
              </span>
              <button
                type="button"
                onClick={() => removeAttachment(a)}
                aria-label={`Remove ${a.name}`}
                className="absolute top-1.5 right-1.5 flex size-5 items-center justify-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                <X className="size-3.5" />
              </button>
              {a.status === "uploading" && (
                <span
                  className="absolute bottom-0 left-0 h-0.5 bg-step-docs transition-[width]"
                  style={{ width: `${Math.max(a.progress, 0.05) * 100}%` }}
                  aria-hidden
                />
              )}
            </li>
          ))}
        </ul>
      )}

      <div className="flex items-end gap-1">
        <input
          ref={fileInput}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files) addFiles(e.target.files)
            e.target.value = ""
          }}
        />
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-9 shrink-0 rounded-full text-muted-foreground"
              onClick={() => fileInput.current?.click()}
              aria-label="Attach PDFs"
            >
              <Paperclip className="size-[1.125rem]" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Attach PDFs (or drop them anywhere)</TooltipContent>
        </Tooltip>
        <label htmlFor="composer" className="sr-only">
          Message ContextAI
        </label>
        <textarea
          id="composer"
          ref={textarea}
          rows={1}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onPaste={(e) => {
            const files = Array.from(e.clipboardData.files)
            if (files.length) {
              e.preventDefault()
              addFiles(files)
            }
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault()
              submit()
            }
          }}
          placeholder={ready.length ? "Ask about your PDF, or press Enter to summarize" : "Ask anything, or attach a PDF"}
          className="max-h-[13.75rem] flex-1 resize-none bg-transparent py-2 pl-1 text-[1rem] leading-relaxed outline-none placeholder:text-muted-foreground"
        />
        <Button
          type="submit"
          size="icon"
          disabled={!streaming && !canSend}
          aria-label={streaming ? "Stop generating" : "Send message"}
          title={streaming ? "Stop (Esc)" : uploading ? "Waiting for uploads" : "Send (Enter)"}
          className={cn("size-9 shrink-0 rounded-full", streaming && "bg-foreground")}
        >
          {streaming ? <Square className="size-3.5 fill-current" /> : <ArrowUp className="size-4.5" />}
        </Button>
      </div>
    </form>
  )
})
