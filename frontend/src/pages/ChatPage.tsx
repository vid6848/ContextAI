import { FileText } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router"
import { toast } from "sonner"

import { Composer, type ComposerHandle } from "@/components/Composer"
import { EmptyState } from "@/components/EmptyState"
import { ConnectionBanner } from "@/components/ConnectionBanner"
import { AssistantMessage, UserMessage } from "@/components/MessageItem"
import { SourcesPanel } from "@/components/Sources"
import { useConnection } from "@/hooks/useConnection"
import { useStickToBottom } from "@/hooks/useStickToBottom"
import { useActiveMessages, useChat } from "@/store/chat"

export function ChatPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const messages = useActiveMessages()
  const streaming = useChat((s) => !!s.streaming)
  const openConversation = useChat((s) => s.openConversation)
  const send = useChat((s) => s.send)
  const stop = useChat((s) => s.stop)
  const composer = useRef<ComposerHandle>(null)
  const connection = useConnection()
  const { ref: scrollRef, scrollToBottom } = useStickToBottom<HTMLDivElement>(messages)

  useEffect(() => {
    openConversation(id ?? null).catch(() => {
      toast.error("That chat doesn't exist or was deleted.")
      navigate("/", { replace: true })
    })
    composer.current?.focus()
  }, [id, openConversation, navigate])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && useChat.getState().streaming) stop()
      // "/" jumps to the message box unless the user is already typing somewhere
      const typing = e.target instanceof HTMLElement && e.target.closest("input, textarea, [contenteditable]")
      if (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey) {
        e.preventDefault()
        composer.current?.focus()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [stop])

  const onSend = (text: string, attachments: string[] = []) => {
    scrollToBottom()
    void send(text, { attachments, onCreated: (newId) => navigate(`/c/${newId}`, { replace: true }) })
  }

  // Drop PDFs anywhere on the chat to attach them. dragDepth tracks nested enter/leave events.
  const [dragging, setDragging] = useState(false)
  const dragDepth = useRef(0)
  const hasFiles = (e: React.DragEvent) => e.dataTransfer.types.includes("Files")

  return (
    <div
      className="relative flex min-h-0 flex-1 flex-col"
      onDragEnter={(e) => {
        if (!hasFiles(e)) return
        e.preventDefault()
        dragDepth.current += 1
        setDragging(true)
      }}
      onDragOver={(e) => hasFiles(e) && e.preventDefault()}
      onDragLeave={() => {
        dragDepth.current = Math.max(0, dragDepth.current - 1)
        if (dragDepth.current === 0) setDragging(false)
      }}
      onDrop={(e) => {
        if (!hasFiles(e)) return
        e.preventDefault()
        dragDepth.current = 0
        setDragging(false)
        composer.current?.addFiles(e.dataTransfer.files)
      }}
    >
      {dragging && (
        <div className="pointer-events-none absolute inset-3 z-20 flex flex-col items-center justify-center gap-3 rounded-3xl border-2 border-dashed border-step-docs/60 bg-background/90 backdrop-blur-sm">
          <span className="flex size-12 items-center justify-center rounded-2xl bg-step-docs/10 text-step-docs">
            <FileText className="size-6" />
          </span>
          <p className="text-[15px] font-medium">Drop PDFs to attach them</p>
          <p className="text-sm text-muted-foreground">Up to 10 MB each. Only you can see them.</p>
        </div>
      )}
      <div ref={scrollRef} className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        {messages.length === 0 ? (
          <EmptyState onPick={(text) => onSend(text)} />
        ) : (
          <div className="mx-auto w-full max-w-[720px] space-y-8 px-4 pt-6 pb-10">
            {messages.map((m, i) =>
              m.role === "user" ? (
                <UserMessage key={m.key} message={m} />
              ) : (
                <AssistantMessage key={m.key} message={m} isLast={i === messages.length - 1} />
              ),
            )}
          </div>
        )}
      </div>
      <div className="mx-auto w-full max-w-[720px] px-4 pb-3">
        <ConnectionBanner state={connection} />
        <Composer ref={composer} streaming={streaming} onSend={onSend} onStop={stop} />
        <p className="mt-2 text-center text-xs text-muted-foreground">
          ContextAI can make mistakes. Check important information.
        </p>
      </div>
      <SourcesPanel />
    </div>
  )
}
