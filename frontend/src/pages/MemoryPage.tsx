import { Brain, Check, Pencil, Plus, Search, Trash2, X } from "lucide-react"
import { useCallback, useEffect, useMemo, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { api } from "@/lib/api"
import type { Memory } from "@/lib/types"
import { cn } from "@/lib/utils"

function relative(iso?: string | null) {
  if (!iso) return ""
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)
  if (days <= 0) return "today"
  if (days === 1) return "yesterday"
  if (days < 30) return `${days} days ago`
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })
}

function MemoryRow({ memory, onChanged }: { memory: Memory; onChanged: () => void }) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(memory.fact)

  const save = async () => {
    const next = text.trim()
    if (!next || next === memory.fact) return setEditing(false)
    try {
      await api.editMemory(memory.id, next)
      setEditing(false)
      onChanged()
    } catch {
      toast.error("Couldn't save that change.")
    }
  }

  const remove = async () => {
    try {
      await api.deleteMemory(memory.id)
      toast("Forgotten")
      onChanged()
    } catch {
      toast.error("Couldn't delete that memory.")
    }
  }

  return (
    <li className="group flex items-start gap-3 rounded-2xl border bg-card/80 p-3 sm:gap-3.5 sm:p-4 shadow-[0_14px_34px_-28px_rgb(30_20_90/0.45)] backdrop-blur-xl">
      <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-xl bg-step-memory/12 text-step-memory">
        <Brain className="size-4" />
      </span>
      <div className="min-w-0 flex-1">
        {editing ? (
          <input
            autoFocus
            value={text}
            maxLength={300}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") save()
              if (e.key === "Escape") {
                setText(memory.fact)
                setEditing(false)
              }
            }}
            aria-label="Memory"
            className="w-full rounded-lg border border-brand/40 bg-background px-2.5 py-1.5 text-[1rem] outline-none"
          />
        ) : (
          <p className="text-[1rem] leading-snug [overflow-wrap:anywhere]">{memory.fact}</p>
        )}
        <p className="mt-1 text-[0.82rem] text-muted-foreground">
          {memory.source === "manual" ? "Added by you" : "Learned from a chat"}
          {memory.updated_at ? `, ${relative(memory.updated_at)}` : ""}
        </p>
      </div>
      <div className={cn("flex shrink-0 gap-0.5", !editing && "opacity-0 group-hover:opacity-100 focus-within:opacity-100 max-md:opacity-100 touch:opacity-100")}>
        {editing ? (
          <>
            <Button variant="ghost" size="icon" aria-label="Save" onClick={save}>
              <Check className="size-4" />
            </Button>
            <Button variant="ghost" size="icon" aria-label="Cancel" onClick={() => setEditing(false)}>
              <X className="size-4" />
            </Button>
          </>
        ) : (
          <>
            <Button variant="ghost" size="icon" aria-label={`Edit "${memory.fact}"`} onClick={() => setEditing(true)}>
              <Pencil className="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label={`Forget "${memory.fact}"`}
              onClick={remove}
              className="hover:text-destructive"
            >
              <Trash2 className="size-4" />
            </Button>
          </>
        )}
      </div>
    </li>
  )
}

export function MemoryPage() {
  const [memories, setMemories] = useState<Memory[] | null>(null)
  const [query, setQuery] = useState("")
  const [draft, setDraft] = useState("")
  const [confirmAll, setConfirmAll] = useState(false)

  const refresh = useCallback(() => api.listMemories().then(setMemories).catch(() => setMemories([])), [])
  useEffect(() => {
    void refresh()
  }, [refresh])

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (memories ?? []).filter((m) => !q || m.fact.toLowerCase().includes(q))
  }, [memories, query])

  const add = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!draft.trim()) return
    try {
      await api.addMemory(draft.trim())
      setDraft("")
      toast.success("Remembered")
      refresh()
    } catch {
      toast.error("Couldn't add that.")
    }
  }

  const forgetAll = async () => {
    try {
      await api.forgetEverything()
      setConfirmAll(false)
      toast("ContextAI forgot everything about you")
      refresh()
    } catch {
      toast.error("Couldn't clear your memories.")
    }
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-[52rem] px-4 pt-6 pb-[max(4rem,env(safe-area-inset-bottom))] sm:px-5 sm:pt-8">
        <h1 className="animate-rise font-display text-[clamp(2.25rem,4vw,3.25rem)] leading-tight font-semibold tracking-[-0.03em]">
          What ContextAI <span className="text-gradient">remembers</span>
        </h1>
        <p className="mt-3 max-w-[56ch] text-[1.05rem] leading-relaxed text-muted-foreground">
          Facts it picked up from your chats so it can personalise answers later. Edit anything that's wrong, or
          delete what you'd rather it forgot.
        </p>

        <form onSubmit={add} className="mt-8 flex gap-2">
          <input
            value={draft}
            maxLength={300}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="e.g. I prefer short answers"
            aria-label="New memory"
            className="h-12 min-w-0 flex-1 rounded-2xl border bg-card/80 px-4 text-[1rem] backdrop-blur-xl outline-none focus:border-brand/50"
          />
          <Button type="submit" disabled={!draft.trim()} className="h-12 shrink-0 rounded-2xl px-4 sm:px-5">
            <Plus /> Add
          </Button>
        </form>

        {(memories?.length ?? 0) > 3 && (
          <div className="relative mt-6">
            <Search className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search memories"
              aria-label="Search memories"
              className="h-11 w-full rounded-xl bg-transparent pr-3 pl-10 outline-none hover:bg-accent/60 focus:bg-accent/60"
            />
          </div>
        )}

        <ul className="mt-6 space-y-3">
          {memories === null && <li className="text-muted-foreground">Loading…</li>}
          {memories?.length === 0 && (
            <li className="rounded-2xl border border-dashed p-8 text-center text-muted-foreground">
              Nothing yet. Mention things like where you live or how you like answers, and ContextAI will remember
              them.
            </li>
          )}
          {shown.map((m) => (
            <MemoryRow key={m.id} memory={m} onChanged={refresh} />
          ))}
          {memories && memories.length > 0 && shown.length === 0 && (
            <li className="text-muted-foreground">No memories match that search.</li>
          )}
        </ul>

        {memories && memories.length > 0 && (
          <Button variant="ghost" className="mt-8 text-muted-foreground hover:text-destructive" onClick={() => setConfirmAll(true)}>
            <Trash2 /> Forget everything
          </Button>
        )}
      </div>

      <Dialog open={confirmAll} onOpenChange={setConfirmAll}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Forget everything?</DialogTitle>
            <DialogDescription>
              This deletes all {memories?.length} memories. Your chats and documents are kept. This can't be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmAll(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={forgetAll}>
              Forget everything
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
