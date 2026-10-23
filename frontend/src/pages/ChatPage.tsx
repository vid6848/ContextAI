import { useEffect, useRef } from "react"
import { useNavigate, useParams } from "react-router"
import { toast } from "sonner"

import { Composer, type ComposerHandle } from "@/components/Composer"
import { EmptyState } from "@/components/EmptyState"
import { AssistantMessage, UserMessage } from "@/components/MessageItem"
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
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [stop])

  const onSend = (text: string) => {
    scrollToBottom()
    void send(text, { onCreated: (newId) => navigate(`/c/${newId}`, { replace: true }) })
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div ref={scrollRef} className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        {messages.length === 0 ? (
          <EmptyState onPick={onSend} />
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
        <Composer ref={composer} streaming={streaming} onSend={onSend} onStop={stop} />
        <p className="mt-2 text-center text-xs text-muted-foreground">
          ContextAI can make mistakes. Check important information.
        </p>
      </div>
    </div>
  )
}
