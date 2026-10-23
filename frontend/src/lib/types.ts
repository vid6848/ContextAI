export type StepStatus = "running" | "done" | "error"

/** One unit of agent work (memory recall, routing, a tool call, document search). */
export interface AgentStep {
  id: string
  label: string
  status: StepStatus
  duration_ms?: number
  detail?: unknown
}

export interface Source {
  document: string
  page: number
}

export interface MessageMeta {
  intent?: string | null
  confidence?: number | null
  tool_used?: string | null
  sources?: Source[] | null
  steps?: AgentStep[]
  stopped?: boolean
  feedback?: Feedback
  /** PDFs attached to a user message. */
  attachments?: string[]
}

export type Feedback = "up" | "down"

export interface ChatMessage {
  /** Server id; undefined until the server has saved the message. */
  id?: number
  /** Stable client-side key for rendering. */
  key: string
  role: "user" | "assistant"
  content: string
  meta?: MessageMeta
  streaming?: boolean
  error?: string
}

export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface Reminder {
  id: number
  reminder_text: string
  scheduled_time: string
  created_at: string
  status: "pending" | "completed"
}

/** Server-Sent Events emitted by POST /api/v1/chat/stream. */
export type StreamEvent =
  | { event: "meta"; data: { conversation_id: string; title: string } }
  | { event: "step"; data: AgentStep }
  | { event: "token"; data: { text: string } }
  | { event: "title"; data: { title: string } }
  | {
      event: "done"
      data: MessageMeta & { user_message_id?: number; assistant_message_id?: number }
    }
  | { event: "error"; data: { detail: string } }
