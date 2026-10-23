import { Check, FileText, LoaderCircle, Trash2, Upload } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router"
import { toast } from "sonner"

import type { Panel } from "@/components/AppSidebar"
import { ShortcutsDialog } from "@/components/ShortcutsDialog"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { api, uploadWithProgress } from "@/lib/api"
import type { DocumentInfo, Reminder } from "@/lib/types"
import { cn } from "@/lib/utils"
import { formatWhen } from "@/lib/when"
import { useChat } from "@/store/chat"

export function Panels({ open, onClose }: { open: Panel | null; onClose: () => void }) {
  return (
    <>
      <DocumentsDialog open={open === "documents"} onClose={onClose} />
      <RemindersDialog open={open === "reminders"} onClose={onClose} />
      <ClearMemoryDialog open={open === "memory"} onClose={onClose} />
      <ShortcutsDialog open={open === "shortcuts"} onClose={onClose} />
    </>
  )
}

function formatDate(iso?: string | null) {
  if (!iso) return ""
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })
}

function DocumentsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [docs, setDocs] = useState<DocumentInfo[] | null>(null)
  const [progress, setProgress] = useState<number | null>(null)
  const input = useRef<HTMLInputElement>(null)

  const refresh = useCallback(() => api.listDocuments().then(setDocs).catch(() => setDocs([])), [])
  useEffect(() => {
    if (open) refresh()
  }, [open, refresh])

  const upload = async (file: File) => {
    setProgress(0)
    try {
      const res = await uploadWithProgress(file, setProgress)
      toast.success(`Added ${res.document_name}`)
      refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Upload failed.")
    } finally {
      setProgress(null)
      if (input.current) input.current.value = ""
    }
  }

  const remove = async (doc: DocumentInfo) => {
    try {
      await api.deleteDocument(doc.document_id)
      toast(`Deleted ${doc.document_name}`)
      refresh()
    } catch {
      toast.error("Couldn't delete the document.")
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Your documents</DialogTitle>
          <DialogDescription>
            ContextAI searches these when you ask about your files. Only you can see them.
          </DialogDescription>
        </DialogHeader>
        <ul className="max-h-80 divide-y overflow-y-auto">
          {docs === null && <li className="py-3 text-sm text-muted-foreground">Loading…</li>}
          {docs?.length === 0 && (
            <li className="py-3 text-sm text-muted-foreground">
              No documents yet. Add a PDF here, or drop one into any chat.
            </li>
          )}
          {docs?.map((d) => (
            <li key={d.document_id} className="flex items-center gap-3 py-2.5">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-step-docs/12 text-step-docs">
                <FileText className="size-4" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{d.document_name}</p>
                <p className="text-xs text-muted-foreground">
                  {d.pages} {d.pages === 1 ? "page" : "pages"}, {d.chunks} passages
                  {d.uploaded_at ? `, added ${formatDate(d.uploaded_at)}` : ""}
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Delete ${d.document_name}`}
                onClick={() => remove(d)}
                className="text-muted-foreground hover:text-destructive"
              >
                <Trash2 className="size-4" />
              </Button>
            </li>
          ))}
        </ul>
        <input
          ref={input}
          type="file"
          accept="application/pdf,.pdf"
          hidden
          onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
        />
        <DialogFooter>
          <Button onClick={() => input.current?.click()} disabled={progress !== null}>
            {progress !== null ? <LoaderCircle className="animate-spin" /> : <Upload />}
            {progress === null ? "Add a PDF" : progress < 1 ? `Uploading ${Math.round(progress * 100)}%` : "Reading the PDF…"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function RemindersDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [reminders, setReminders] = useState<Reminder[]>([])
  const [text, setText] = useState("")
  const [when, setWhen] = useState("")
  const [permission, setPermission] = useState(() => ("Notification" in window ? Notification.permission : "denied"))

  // Captured when the list loads, so "overdue" is computed without reading the clock during render
  const [checkedAt, setCheckedAt] = useState(0)
  const refresh = useCallback(
    () =>
      api
        .listReminders()
        .then((list) => {
          setReminders(list)
          setCheckedAt(Date.now())
        })
        .catch(() => setReminders([])),
    [],
  )
  useEffect(() => {
    if (open) refresh()
  }, [open, refresh])

  const create = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!text.trim() || !when) return
    try {
      await api.createReminder(text, when)
      setText("")
      setWhen("")
      toast.success("Reminder added")
      refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't add the reminder.")
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Reminders</DialogTitle>
          <DialogDescription>
            Add them here or just ask in chat: "remind me to call mom tomorrow at 6".
          </DialogDescription>
        </DialogHeader>
        {permission === "default" && (
          <div className="flex items-center justify-between gap-3 rounded-xl border border-brand/25 bg-brand/[0.06] px-3.5 py-2.5 text-sm">
            <span>Get a notification when a reminder is due, even in another tab.</span>
            <Button
              size="sm"
              variant="outline"
              onClick={async () => setPermission(await Notification.requestPermission())}
            >
              Turn on
            </Button>
          </div>
        )}
        <form onSubmit={create} className="flex flex-col gap-2 sm:flex-row">
          <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Call the dentist" aria-label="Reminder" />
          <Input
            value={when}
            onChange={(e) => setWhen(e.target.value)}
            placeholder="tomorrow at 5pm"
            aria-label="When"
            className="sm:w-48"
          />
          <Button type="submit" disabled={!text.trim() || !when}>
            Add
          </Button>
        </form>
        <ul className="max-h-72 divide-y overflow-y-auto">
          {reminders.length === 0 && <li className="py-3 text-sm text-muted-foreground">No reminders yet.</li>}
          {reminders.map((r) => {
            const done = r.status === "completed"
            return (
              <li key={r.id} className="flex items-center gap-3 py-2.5">
                <button
                  type="button"
                  disabled={done}
                  aria-label={done ? "Completed" : `Mark "${r.reminder_text}" done`}
                  onClick={() => api.completeReminder(r.id).then(refresh)}
                  className={cn(
                    "flex size-5 shrink-0 items-center justify-center rounded-full border",
                    done && "border-step-docs bg-step-docs text-white",
                  )}
                >
                  {done && <Check className="size-3" />}
                </button>
                <div className="min-w-0 flex-1">
                  <p className={cn("truncate text-sm", done && "text-muted-foreground line-through")}>{r.reminder_text}</p>
                  <p className={cn("text-xs text-muted-foreground", !done && r.due_at && checkedAt > 0 && Date.parse(r.due_at) < checkedAt && "text-step-error")}>
                    {r.due_at ? formatWhen(r.due_at) : r.scheduled_time}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Delete "${r.reminder_text}"`}
                  onClick={() => api.deleteReminder(r.id).then(refresh)}
                  className="text-muted-foreground"
                >
                  <Trash2 className="size-4" />
                </Button>
              </li>
            )
          })}
        </ul>
      </DialogContent>
    </Dialog>
  )
}

function ClearMemoryDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const reset = useChat((s) => s.reset)
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)

  const clear = async () => {
    setBusy(true)
    try {
      await api.clearMemory()
      reset()
      navigate("/chat")
      toast.success("Chats and memory cleared")
      onClose()
    } catch {
      toast.error("Couldn't clear your data. Try again.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Clear chats and memory?</DialogTitle>
          <DialogDescription>
            This deletes every chat and everything ContextAI remembers about you. Your documents are kept. This can't
            be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={clear} disabled={busy}>
            {busy ? "Clearing…" : "Clear chats and memory"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
