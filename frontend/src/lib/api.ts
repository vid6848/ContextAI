import { parseSSE } from "./sse"
import type { Conversation, DocumentInfo, Feedback, Memory, Reminder, StreamEvent } from "./types"

const API = "/api/v1"
const USER_KEY = "contextai_user_id"

/** Anonymous per-browser identity until real sign-in lands (issue #17). */
export const userId: string = (() => {
  try {
    let id = localStorage.getItem(USER_KEY)
    if (!id) {
      id = crypto.randomUUID()
      localStorage.setItem(USER_KEY, id)
    }
    return id
  } catch {
    return crypto.randomUUID()
  }
})()

/** The browser's IANA timezone, so "tomorrow at 5pm" means 5pm where the user is. */
export const timezone: string = (() => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone
  } catch {
    return "UTC"
  }
})()

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const sep = path.includes("?") ? "&" : "?"
  const resp = await fetch(`${API}${path}${sep}user_id=${encodeURIComponent(userId)}`, {
    ...init,
    headers: init.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init.headers },
  })
  if (!resp.ok) throw new ApiError(resp.status, await errorDetail(resp))
  return resp.json() as Promise<T>
}

async function errorDetail(resp: Response): Promise<string> {
  try {
    const body = await resp.json()
    if (typeof body.detail === "string") return body.detail
    return "The request was invalid."
  } catch {
    return resp.status === 429 ? "Too many requests. Wait a moment and try again." : `Request failed (${resp.status}).`
  }
}

export interface ServerMessage {
  id: number
  role: "user" | "assistant"
  message: string
  timestamp: string
  metadata: Record<string, unknown> | null
}

export const api = {
  listConversations: () => request<{ conversations: Conversation[] }>("/conversations").then((r) => r.conversations),
  getMessages: (id: string) =>
    request<{ conversation: Conversation; messages: ServerMessage[] }>(`/conversations/${id}/messages`),
  renameConversation: (id: string, title: string) =>
    request(`/conversations/${id}`, { method: "PATCH", body: JSON.stringify({ title }) }),
  deleteConversation: (id: string) => request(`/conversations/${id}`, { method: "DELETE" }),
  setFeedback: (conversationId: string, messageId: number, rating: Feedback | null) =>
    request(`/conversations/${conversationId}/messages/${messageId}/feedback`, {
      method: "PUT",
      body: JSON.stringify({ rating }),
    }),

  listDocuments: () => request<{ documents: DocumentInfo[] }>("/documents").then((r) => r.documents),
  deleteDocument: (id: string) => request(`/documents/${id}`, { method: "DELETE" }),
  listMemories: () => request<{ memories: Memory[] }>("/memories").then((r) => r.memories),
  addMemory: (fact: string) => request<{ id: string; fact: string }>("/memories", { method: "POST", body: JSON.stringify({ fact }) }),
  editMemory: (id: string, fact: string) => request(`/memories/${id}`, { method: "PATCH", body: JSON.stringify({ fact }) }),
  deleteMemory: (id: string) => request(`/memories/${id}`, { method: "DELETE" }),
  forgetEverything: () => request("/memories", { method: "DELETE" }),
  clearMemory: () => request("/memory/clear", { method: "POST", body: JSON.stringify({ user_id: userId }) }),

  listReminders: () => request<{ reminders: Reminder[] }>("/reminders").then((r) => r.reminders),
  createReminder: (reminder_text: string, scheduled_time: string) =>
    request("/reminders", {
      method: "POST",
      body: JSON.stringify({ reminder_text, scheduled_time, timezone, user_id: userId }),
    }),
  parseWhen: (when: string) =>
    request<{ due_at: string | null }>(
      `/reminders/parse?when=${encodeURIComponent(when)}&timezone=${encodeURIComponent(timezone)}`,
    ).then((r) => r.due_at),
  dueReminders: () => request<{ reminders: Reminder[] }>("/reminders/due").then((r) => r.reminders),
  markNotified: (id: number) => request(`/reminders/${id}/notified`, { method: "PATCH" }),
  completeReminder: (id: number) => request(`/reminders/${id}/complete`, { method: "PATCH" }),
  deleteReminder: (id: number) => request(`/reminders/${id}`, { method: "DELETE" }),
}

export interface UploadResult {
  document_name: string
  total_pages: number
  total_chunks: number
}

export const MAX_UPLOAD_MB = 10

/** Upload a PDF with progress (fetch can't report upload progress, XHR can). */
export function uploadWithProgress(file: File, onProgress: (fraction: number) => void, signal?: AbortSignal) {
  return new Promise<UploadResult>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open("POST", `${API}/documents/upload?user_id=${encodeURIComponent(userId)}`)
    xhr.responseType = "json"
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total)
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) return resolve(xhr.response as UploadResult)
      const detail = xhr.response?.detail
      reject(new ApiError(xhr.status, typeof detail === "string" ? detail : `Upload failed (${xhr.status}).`))
    }
    xhr.onerror = () => reject(new ApiError(0, "Upload failed. Check your connection."))
    xhr.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"))
    signal?.addEventListener("abort", () => xhr.abort())
    const form = new FormData()
    form.append("file", file)
    xhr.send(form)
  })
}

export interface StreamRequest {
  message: string
  attachments?: string[]
  conversation_id: string | null
  replace_from_message_id?: number | null
}

/** Stream a chat turn. Abort the signal to stop generation; the server keeps the partial answer. */
export async function* streamChat(req: StreamRequest, signal: AbortSignal): AsyncGenerator<StreamEvent> {
  const resp = await fetch(`${API}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...req, user_id: userId, timezone }),
    signal,
  })
  if (!resp.ok || !resp.body) throw new ApiError(resp.status, await errorDetail(resp))
  for await (const e of parseSSE(resp.body)) yield e as StreamEvent
}
