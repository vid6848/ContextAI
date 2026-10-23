import { Check, Trash2 } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { useNavigate } from "react-router"
import { toast } from "sonner"

import type { Panel } from "@/components/AppSidebar"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { api } from "@/lib/api"
import type { Reminder } from "@/lib/types"
import { cn } from "@/lib/utils"
import { useChat } from "@/store/chat"

export function Panels({ open, onClose }: { open: Panel | null; onClose: () => void }) {
  return (
    <>
      <RemindersDialog open={open === "reminders"} onClose={onClose} />
      <ClearMemoryDialog open={open === "memory"} onClose={onClose} />
    </>
  )
}

function RemindersDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [reminders, setReminders] = useState<Reminder[]>([])
  const [text, setText] = useState("")
  const [when, setWhen] = useState("")

  const refresh = useCallback(() => api.listReminders().then(setReminders).catch(() => setReminders([])), [])
  useEffect(() => {
    if (open) refresh()
  }, [open, refresh])

  const create = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!text.trim() || !when) return
    try {
      await api.createReminder(text, when.replace("T", " "))
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
          <DialogDescription>Things you asked ContextAI to keep track of.</DialogDescription>
        </DialogHeader>
        <form onSubmit={create} className="flex flex-col gap-2 sm:flex-row">
          <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Call the dentist" aria-label="Reminder" />
          <Input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} aria-label="When" className="sm:w-56" />
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
                  <p className="text-xs text-muted-foreground">{r.scheduled_time}</p>
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
      navigate("/")
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
