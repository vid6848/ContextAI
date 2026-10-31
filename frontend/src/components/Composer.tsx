import { ArrowUp, FileText, LoaderCircle, Paperclip, RotateCw, Square, TriangleAlert, X } from "lucide-react"
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { isTouchDevice, useMediaQuery } from "@/hooks/useMediaQuery"
import { MAX_UPLOAD_MB, uploadWithProgress, type UploadResult } from "@/lib/api"
import { cn } from "@/lib/utils"

const MAX_ATTACHMENTS = 5

interface Attachment {
  id: string
  name: string
  status: "uploading" | "ready" | "error"
  progress: number
  detail?: string
  controller: AbortController
  file: File
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

function uploadSummary(res: UploadResult) {
  const pages = `${res.total_pages} ${res.total_pages === 1 ? "page" : "pages"}`
  if (res.note) return `${pages}, ${res.note}`
  return res.scanned_pages ? `${pages}, scanned` : pages
}

export const Composer = forwardRef<ComposerHandle, ComposerProps>(function Composer({ streaming, onSend, onStop }, ref) {
  const [value, setValue] = useState("")
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const textarea = useRef<HTMLTextAreaElement>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  const update = (id: string, patch: Partial<Attachment>) =>
    setAttachments((list) => list.map((a) => (a.id === id ? { ...a, ...patch } : a)))

  const upload = (att: Attachment) => {
    uploadWithProgress(att.file, (p) => update(att.id, { progress: p }), att.controller.signal)
      .then((res) => update(att.id, { status: "ready", progress: 1, name: res.document_name, detail: uploadSummary(res) }))
      .catch((err: Error) => {
        if (err.name === "AbortError") return
        update(att.id, { status: "error", detail: err.message })
      })
  }

  const retry = (att: Attachment) => {
    const again = { ...att, controller: new AbortController(), status: "uploading" as const, progress: 0, detail: undefined }
    update(att.id, again)
    upload(again)
  }

  const addFiles = (files: FileList | File[]) => {
    const pdfs = Array.from(files).filter((f) => {
      // iOS Files and some Android pickers report an empty or non-standard type, so the extension counts too
      if (!/pdf/i.test(f.type) && !f.name.toLowerCase().endsWith(".pdf")) {
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
        file,
      }
      setAttachments((list) => [...list, att])
      upload(att)
    }
    // On phones and tablets this would pop the keyboard up over the upload progress
    if (!isTouchDevice()) textarea.current?.focus()
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

  const narrow = useMediaQuery("(max-width: 639px)")
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
      className="rounded-[1.75rem] border bg-card/85 p-2 shadow-[0_1px_2px_rgb(0_0_0/0.04),0_18px_40px_-20px_rgb(40_25_120/0.35)] backdrop-blur-xl transition-[border-color,box-shadow] focus-within:border-brand/50 focus-within:shadow-[0_0_0_4px_color-mix(in_oklab,var(--brand)_14%,transparent),0_18px_40px_-20px_rgb(40_25_120/0.4)]"
    >
      {attachments.length > 0 && (
        <ul
          className="flex max-h-[24dvh] flex-wrap items-start gap-2 overflow-y-auto px-1 pt-1 pb-2 max-sm:flex-nowrap max-sm:overflow-x-auto"
          aria-label="Attached files"
        >
          {attachments.map((a) => (
            <li
              key={a.id}
              className={cn(
                "relative flex max-w-full items-center max-sm:max-w-[85%] max-sm:shrink-0 sm:max-w-[15rem] gap-2.5 overflow-hidden rounded-xl border bg-background py-2 pr-8 pl-2.5",
                a.status === "error" && "border-step-error/40 pr-16 sm:max-w-[20rem]",
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
                <span className={cn("block truncate text-xs text-muted-foreground", a.status === "error" && "whitespace-normal text-step-error")}>
                  {a.status === "uploading"
                    ? a.progress < 1
                      ? `Uploading ${Math.round(a.progress * 100)}%`
                      : "Reading the PDF…"
                    : a.detail}
                </span>
              </span>
              {a.status === "error" && (
                <button
                  type="button"
                  onClick={() => retry(a)}
                  aria-label={`Try uploading ${a.name} again`}
                  className="absolute right-8 top-1 flex size-7 items-center justify-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground"
                >
                  <RotateCw className="size-3.5" />
                </button>
              )}
              <button
                type="button"
                onClick={() => removeAttachment(a)}
                aria-label={`Remove ${a.name}`}
                className="absolute top-1 right-1 flex size-7 items-center justify-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground"
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
              className="size-10 shrink-0 rounded-full text-muted-foreground"
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
          enterKeyHint="send"
          placeholder={
            ready.length
              ? narrow
                ? "Ask about your PDF"
                : "Ask about your PDF, or press Enter to summarize"
              : narrow
                ? "Ask anything"
                : "Ask anything, or attach a PDF"
          }
          className="max-h-[min(13.75rem,24dvh)] min-w-0 flex-1 resize-none bg-transparent py-2 pl-1 text-[1rem] leading-relaxed outline-none placeholder:text-muted-foreground"
        />
        <Button
          type="submit"
          size="icon"
          disabled={!streaming && !canSend}
          aria-label={streaming ? "Stop generating" : "Send message"}
          title={streaming ? "Stop (Esc)" : uploading ? "Waiting for uploads" : "Send (Enter)"}
          className={cn(
            "size-10 shrink-0 rounded-full border-0 text-white shadow-[0_6px_16px_-6px_rgb(91_71_245/0.6)] disabled:opacity-35 disabled:shadow-none",
            streaming ? "bg-foreground text-background" : "bg-brand-gradient hover:brightness-110",
          )}
        >
          {streaming ? <Square className="size-3.5 fill-current" /> : <ArrowUp className="size-4.5" />}
        </Button>
      </div>
    </form>
  )
})
