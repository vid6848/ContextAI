import { create } from "zustand"

import { api, streamChat, type ServerMessage } from "@/lib/api"
import type { AgentStep, ChatMessage, Conversation, Feedback, MessageMeta } from "@/lib/types"

/** Messages of a chat that hasn't been sent yet live under this key until the server assigns an id. */
export const DRAFT = "__draft__"

let keySeq = 0
const newKey = () => `m${Date.now().toString(36)}${(keySeq++).toString(36)}`

export function fromServer(m: ServerMessage): ChatMessage {
  return {
    id: m.id,
    key: `s${m.id}`,
    role: m.role,
    content: m.message,
    meta: (m.metadata as MessageMeta | null) ?? undefined,
  }
}

interface SendOptions {
  /** Edit/regenerate: drop this user message (and everything after it) before sending. */
  replaceFromKey?: string
  /** Called once when a draft chat gets its server id, so the route can follow. */
  onCreated?: (conversationId: string) => void
  /** Names of uploaded PDFs this message is about. */
  attachments?: string[]
}

interface ChatState {
  conversations: Conversation[]
  conversationsLoaded: boolean
  messages: Record<string, ChatMessage[]>
  activeId: string | null
  streaming: { chatKey: string; controller: AbortController } | null

  loadConversations: () => Promise<void>
  openConversation: (id: string | null) => Promise<void>
  send: (text: string, opts?: SendOptions) => Promise<void>
  stop: () => void
  regenerate: (assistantKey: string) => void
  edit: (userKey: string, text: string) => void
  setFeedback: (messageKey: string, rating: Feedback | null) => Promise<void>
  rename: (id: string, title: string) => Promise<void>
  remove: (id: string) => Promise<void>
  reset: () => void
}

export const useChat = create<ChatState>((set, get) => {
  const chatKey = () => get().activeId ?? DRAFT

  const patchMessage = (ck: string, key: string, fn: (m: ChatMessage) => ChatMessage) =>
    set((s) => ({ messages: { ...s.messages, [ck]: (s.messages[ck] ?? []).map((m) => (m.key === key ? fn(m) : m)) } }))

  const upsertStep = (steps: AgentStep[] = [], step: AgentStep) => {
    const i = steps.findIndex((s) => s.id === step.id)
    return i < 0 ? [...steps, step] : steps.map((s, j) => (j === i ? step : s))
  }

  return {
    conversations: [],
    conversationsLoaded: false,
    messages: { [DRAFT]: [] },
    activeId: null,
    streaming: null,

    async loadConversations() {
      try {
        set({ conversations: await api.listConversations(), conversationsLoaded: true })
      } catch {
        set({ conversationsLoaded: true })
      }
    },

    async openConversation(id) {
      if (id === get().activeId && (id === null || get().messages[id])) return
      if (id === null) {
        set((s) => ({ activeId: null, messages: { ...s.messages, [DRAFT]: s.streaming ? s.messages[DRAFT] : [] } }))
        return
      }
      set({ activeId: id })
      if (get().messages[id]) return
      const { messages } = await api.getMessages(id)
      set((s) => ({ messages: { ...s.messages, [id]: messages.map(fromServer) } }))
    },

    async send(text, opts = {}) {
      const clean = text.trim()
      if (!clean || get().streaming) return

      let ck = chatKey()
      let history = get().messages[ck] ?? []
      let replaceFromId: number | null = null
      if (opts.replaceFromKey) {
        const idx = history.findIndex((m) => m.key === opts.replaceFromKey)
        if (idx >= 0) {
          replaceFromId = history[idx].id ?? null
          history = history.slice(0, idx)
        }
      }

      // Edit/regenerate keeps the attachments of the message being replaced
      const replaced = opts.replaceFromKey ? get().messages[ck]?.find((m) => m.key === opts.replaceFromKey) : undefined
      const attachments = opts.attachments ?? replaced?.meta?.attachments ?? []
      const user: ChatMessage = {
        key: newKey(),
        role: "user",
        content: clean,
        meta: attachments.length ? { attachments } : undefined,
      }
      const reply: ChatMessage = { key: newKey(), role: "assistant", content: "", streaming: true, meta: { steps: [] } }
      const controller = new AbortController()
      set((s) => ({ messages: { ...s.messages, [ck]: [...history, user, reply] }, streaming: { chatKey: ck, controller } }))

      try {
        const stream = streamChat(
          { message: clean, attachments, conversation_id: get().activeId, replace_from_message_id: replaceFromId },
          controller.signal,
        )
        for await (const { event, data } of stream) {
          switch (event) {
            case "meta":
              if (ck === DRAFT) {
                const id = data.conversation_id
                const now = new Date().toISOString()
                set((s) => ({
                  activeId: id,
                  messages: { ...s.messages, [id]: s.messages[DRAFT], [DRAFT]: [] },
                  streaming: s.streaming && { ...s.streaming, chatKey: id },
                  conversations: [{ id, title: data.title, created_at: now, updated_at: now }, ...s.conversations],
                }))
                ck = id
                opts.onCreated?.(id)
              }
              break
            case "step":
              patchMessage(ck, reply.key, (m) => ({ ...m, meta: { ...m.meta, steps: upsertStep(m.meta?.steps, data) } }))
              break
            case "token":
              patchMessage(ck, reply.key, (m) => ({ ...m, content: m.content + data.text }))
              break
            case "title":
              set((s) => ({ conversations: s.conversations.map((c) => (c.id === ck ? { ...c, title: data.title } : c)) }))
              break
            case "done": {
              const { user_message_id, assistant_message_id, ...meta } = data
              patchMessage(ck, user.key, (m) => ({ ...m, id: user_message_id }))
              patchMessage(ck, reply.key, (m) => ({ ...m, id: assistant_message_id, meta: { ...m.meta, ...meta } }))
              break
            }
            case "memory":
              patchMessage(ck, reply.key, (m) => ({ ...m, meta: { ...m.meta, memory: data.changes } }))
              break
            case "error":
              patchMessage(ck, reply.key, (m) => ({ ...m, error: data.detail }))
              break
          }
        }
      } catch (err) {
        if (controller.signal.aborted) {
          patchMessage(ck, reply.key, (m) => ({ ...m, meta: { ...m.meta, stopped: true } }))
        } else {
          const detail = err instanceof Error ? err.message : String(err)
          patchMessage(ck, reply.key, (m) => ({ ...m, error: detail || "Couldn't reach the server." }))
        }
      } finally {
        patchMessage(ck, reply.key, (m) => ({ ...m, streaming: false }))
        set({ streaming: null })
      }

      void get().loadConversations()
      // A stopped answer is saved server-side once generation halts; refetch to learn its message ids.
      if (controller.signal.aborted && ck !== DRAFT) {
        const target = ck
        setTimeout(async () => {
          if (get().streaming) return
          try {
            const { messages } = await api.getMessages(target)
            set((s) => ({ messages: { ...s.messages, [target]: messages.map(fromServer) } }))
          } catch {
            /* keep the local copy */
          }
        }, 1500)
      }
    },

    stop() {
      get().streaming?.controller.abort()
    },

    regenerate(assistantKey) {
      const list = get().messages[chatKey()] ?? []
      const idx = list.findIndex((m) => m.key === assistantKey)
      const user = list[idx - 1]
      if (user?.role === "user") void get().send(user.content, { replaceFromKey: user.key })
    },

    edit(userKey, text) {
      void get().send(text, { replaceFromKey: userKey })
    },

    async setFeedback(messageKey, rating) {
      const ck = chatKey()
      const message = get().messages[ck]?.find((m) => m.key === messageKey)
      if (!message?.id || ck === DRAFT) return
      const previous = message.meta?.feedback
      patchMessage(ck, messageKey, (m) => ({ ...m, meta: { ...m.meta, feedback: rating ?? undefined } }))
      try {
        await api.setFeedback(ck, message.id, rating)
      } catch (err) {
        patchMessage(ck, messageKey, (m) => ({ ...m, meta: { ...m.meta, feedback: previous } }))
        throw err
      }
    },

    async rename(id, title) {
      await api.renameConversation(id, title)
      set((s) => ({ conversations: s.conversations.map((c) => (c.id === id ? { ...c, title } : c)) }))
    },

    async remove(id) {
      await api.deleteConversation(id)
      set((s) => {
        const messages = { ...s.messages }
        delete messages[id]
        return {
          conversations: s.conversations.filter((c) => c.id !== id),
          messages,
          activeId: s.activeId === id ? null : s.activeId,
        }
      })
    },

    reset() {
      set({ conversations: [], messages: { [DRAFT]: [] }, activeId: null })
    },
  }
})

export const useActiveMessages = () => useChat((s) => s.messages[s.activeId ?? DRAFT] ?? EMPTY)
const EMPTY: ChatMessage[] = []
