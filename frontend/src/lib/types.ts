export type StepStatus = "running" | "done" | "error"

/** One unit of agent work (memory recall, routing, a tool call, document search). */
export interface AgentStep {
  id: string
  label: string
  status: StepStatus
  duration_ms?: number
  detail?: unknown
}

/** A citable source: a passage from the user's PDFs or a web search result. `n` matches [n] in the answer. */
export interface Source {
  n?: number
  kind?: "document" | "web"
  document?: string
  page?: number
  title?: string
  url?: string
  excerpt?: string
  /** Heading of the document section the passage sits under. */
  section?: string
}

export interface WeatherOutput {
  location: string
  temperature: number
  feels_like?: number
  humidity?: number
  condition?: string
  description?: string
  wind_speed?: number
  units?: "celsius" | "fahrenheit"
}

export interface ForecastDay {
  date: string
  weekday: string
  high: number | null
  low: number | null
  condition?: string
  description?: string
  rain_chance_percent: number
}

export interface ForecastOutput {
  location: string
  units?: "celsius" | "fahrenheit"
  today: string
  days: ForecastDay[]
  hours?: { time: string; temperature: number; description?: string; rain_chance_percent: number }[]
}

export interface CryptoOutput {
  coin: string
  price_usd: number
  change_24h_percent?: number | null
  market_cap_usd?: number | null
}

export interface MessageMeta {
  intent?: string | null
  confidence?: number | null
  tool_used?: string | null
  sources?: Source[] | null
  /** Structured result of the weather/crypto tool, rendered as a card (single-tool answers). */
  tool_output?: Record<string, unknown> | null
  /** Every card produced while answering; several when the model chained tools. */
  cards?: { tool: string; output: Record<string, unknown> }[]
  tools_used?: string[]
  steps?: AgentStep[]
  stopped?: boolean
  feedback?: Feedback
  /** PDFs attached to a user message. */
  attachments?: string[]
  /** Long-term memory changes made because of this exchange. */
  memory?: MemoryChange[]
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

export interface MemoryChange {
  op: "add" | "update" | "delete"
  id: string
  fact: string
}

export interface Memory {
  id: string
  fact: string
  source: "chat" | "manual"
  created_at?: string | null
  updated_at?: string | null
}

export interface DocumentInfo {
  document_id: string
  document_name: string
  pages: number
  chunks: number
  uploaded_at?: string | null
}

export interface Reminder {
  id: number
  reminder_text: string
  scheduled_time: string
  created_at: string
  status: "pending" | "completed"
  due_at?: string | null
  timezone?: string | null
  notified_at?: string | null
}

export interface ReminderOutput {
  id: number
  text: string
  due_at: string
}

/** Server-Sent Events emitted by POST /api/v1/chat/stream. */
export type StreamEvent =
  | { event: "meta"; data: { conversation_id: string; title: string } }
  | { event: "step"; data: AgentStep }
  | { event: "token"; data: { text: string } }
  | { event: "title"; data: { title: string } }
  | { event: "memory"; data: { changes: MemoryChange[] } }
  | {
      event: "done"
      data: MessageMeta & { user_message_id?: number; assistant_message_id?: number }
    }
  | { event: "error"; data: { detail: string } }
