# ContextAI

**An AI assistant that shows its work.** ContextAI remembers what you tell it, checks live data, and reads your PDFs. Every answer streams in alongside the steps the agent took (memory recall, routing, tool calls, document search) and the sources it used.

> 🚧 ContextAI is being built in public as a [5-phase roadmap](#-roadmap). Every change is tracked as a GitHub issue.

---

## ✨ Features

| | |
|---|---|
| **Tool-using agent** | The model picks tools itself through function calling, runs several in parallel, and chains them: "BTC and ETH prices, and how many ETH per BTC?" fetches both prices, then calls the calculator. A confident TF-IDF classifier still fast-paths simple requests (hybrid router). |
| **Live agent trace** | Each answer opens with a colour-coded rail of the agent's steps: violet memory, blue routing, amber tools, teal documents, red errors. Each step is timed, and you can expand it to see the exact tool input and output. |
| **Streaming chat** | Answers stream token by token over Server-Sent Events, with Stop (Esc), Regenerate, Edit-and-resend, Copy and 👍/👎 feedback. |
| **PDF Q&A with citations** | Drag a PDF into the chat and ask about it. Chunks follow the document's headings, retrieval is re-ranked (semantic + keyword), and off-topic questions get "not in your documents" instead of a guess. Answers cite passages inline as `[1]`, and clicking one opens the exact excerpt, page and section. Manage your documents from the account menu. |
| **Live tools** | CoinGecko crypto prices and OpenWeather (shown as cards), Tavily web search (with source cards and today's date for freshness), and a safe AST-based calculator. |
| **Long-term memory** | After each reply an LLM pass extracts durable facts ("Prefers Python examples") and reconciles them with what's stored: a move *updates* your city instead of contradicting it. A "Memory updated" chip shows what changed, and the Memory page lets you edit or delete anything. |
| **Reminders** | "Remind me to call mom tomorrow evening" works from chat. Times are parsed in your timezone, and due reminders show a toast and a browser notification. |
| **Chat app** | An animated landing page (`/`) and the chat (`/chat`) share one look. Server-side conversations with LLM-written titles, a grouped sidebar with search, rename and delete, light/dark mode, keyboard shortcuts, and a mobile layout. |
| **Rich answers** | Syntax-highlighted code with copy, KaTeX math (prices stay prices), and GFM tables. |
| **Hardening** | Per-browser user isolation, rate limits, streamed upload size caps, PDF validation, and errors that never leak keys or internals. |

---

## 🧱 Architecture

```text
React SPA (Vite, TS, Tailwind, shadcn/ui, Zustand)
   │  REST + Server-Sent Events  (/api/v1/chat/stream: meta → step* → token* → done → memory → title)
   ▼
FastAPI ─────────────────────────────────── serves the built SPA on the same origin
   │
   ▼
LangGraph agent
   retrieve_memory ─▶ classify_intent ─┬─ confident ─▶ fixed tool node ─▶ generate_response ─┐
   (history + facts)  (TF-IDF + LR)    │                                                     ├─▶ save_memory
                                       └─ otherwise ─▶ llm_agent ────────────────────────────┘
                                                       function-calling loop (≤ 4 rounds):
                                                       calculator · weather · crypto · web_search ·
                                                       search_documents · create/list_reminder
   after the reply: LLM memory extraction (add / update / delete facts) · LLM chat title
```

Every node runs inside a timed `agent_step` that streams `running → done/error` events through LangGraph's stream writer. The same graph serves the streaming and the plain JSON endpoint.

## 🛠 Tech Stack

| Layer | Now | Planned |
|---|---|---|
| Frontend | React 19, TypeScript, Vite, Tailwind v4, shadcn/ui, Zustand, React Router | |
| API | FastAPI + Server-Sent Events | |
| Agent | LangGraph, Gemini function calling with multi-tool chaining, TF-IDF + Logistic Regression fast path | |
| LLM | Gemini via LiteLLM (swap providers with one env var) | |
| Data | SQLite + ChromaDB, heading-aware PDF chunking, hybrid re-ranking, dateparser | Supabase Postgres + pgvector ([#18](https://github.com/vid6848/ContextAI/issues/18)) |
| Auth | Anonymous per-browser id | Supabase Auth with Google ([#17](https://github.com/vid6848/ContextAI/issues/17)) |
| Quality | pytest (148), Vitest (18), ruff, oxlint, GitHub Actions | Eval suite ([#20](https://github.com/vid6848/ContextAI/issues/20)), Langfuse ([#21](https://github.com/vid6848/ContextAI/issues/21)) |
| Hosting | Docker (multi-stage), Railway config | Hugging Face Spaces ([#19](https://github.com/vid6848/ContextAI/issues/19)) |

---

## 🗺 Roadmap

Tracked with [milestones](https://github.com/vid6848/ContextAI/milestones) and [issues](https://github.com/vid6848/ContextAI/issues).

### ✅ Phase 1: Foundation & hardening
- [x] [#1](https://github.com/vid6848/ContextAI/issues/1) Server-side conversations with per-conversation history
- [x] [#2](https://github.com/vid6848/ContextAI/issues/2) Streaming chat (SSE) with live agent-step events
- [x] [#3](https://github.com/vid6848/ContextAI/issues/3) Stop, regenerate, and edit-and-resend
- [x] [#4](https://github.com/vid6848/ContextAI/issues/4) Security: user isolation, rate limits, upload limits, safe errors
- [x] [#5](https://github.com/vid6848/ContextAI/issues/5) Pinned deps, slim Docker image, CI

### ✅ Phase 2: Frontend rebuild
- [x] [#6](https://github.com/vid6848/ContextAI/issues/6) [#7](https://github.com/vid6848/ContextAI/issues/7) [#8](https://github.com/vid6848/ContextAI/issues/8) React foundation, app shell, streaming trace
- [x] [#9](https://github.com/vid6848/ContextAI/issues/9) Code highlighting, math, tables, feedback
- [x] [#10](https://github.com/vid6848/ContextAI/issues/10) Drag-and-drop PDF attachments
- [x] [#11](https://github.com/vid6848/ContextAI/issues/11) Inline citations, sources panel, weather and crypto cards
- [x] [#12](https://github.com/vid6848/ContextAI/issues/12) Landing page, shortcuts, connection banner, accessibility

### ✅ Phase 3: Smarter agent
- [x] [#13](https://github.com/vid6848/ContextAI/issues/13) LLM function calling with multi-tool chaining (hybrid router)
- [x] [#14](https://github.com/vid6848/ContextAI/issues/14) RAG upgrade: structure-aware chunking, re-ranking, document management
- [x] [#15](https://github.com/vid6848/ContextAI/issues/15) LLM-extracted long-term memory, with a Memory page
- [x] [#16](https://github.com/vid6848/ContextAI/issues/16) Natural-language reminders with notifications

### Phase 4: Accounts, persistence & deploy
- [ ] [#17](https://github.com/vid6848/ContextAI/issues/17) Supabase Auth (Google) + guest mode
- [ ] [#18](https://github.com/vid6848/ContextAI/issues/18) Supabase Postgres + pgvector persistence
- [ ] [#19](https://github.com/vid6848/ContextAI/issues/19) Deploy to Hugging Face Spaces

### Phase 5: Evals, observability & showcase
- [ ] [#20](https://github.com/vid6848/ContextAI/issues/20) Automated evaluation suite in CI
- [ ] [#21](https://github.com/vid6848/ContextAI/issues/21) Langfuse tracing
- [ ] [#22](https://github.com/vid6848/ContextAI/issues/22) Demo GIF, architecture diagram, design decisions

---

## 🚀 Getting started

**Prerequisites:** Python 3.11+ and Node 20+.

```bash
# 1. Backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # add your GEMINI_API_KEY (and optional tool keys)

# 2. Frontend
cd frontend && npm install && cd ..
```

**Develop** (hot reload on both sides, in two terminals):

```bash
uvicorn src.backend.main:app --reload --port 8000     # API on :8000
cd frontend && npm run dev                            # app on http://localhost:5173
```

**Run it like production** (FastAPI serves the built app):

```bash
cd frontend && npm run build && cd ..
uvicorn src.backend.main:app --port 8000              # http://localhost:8000
```

API docs are at http://localhost:8000/docs.

### Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | ✅ | LLM access ([Google AI Studio](https://aistudio.google.com/)) |
| `MODEL_NAME` / `FALLBACK_MODEL_NAME` | | Any LiteLLM model string |
| `TAVILY_API_KEY` | | Web search tool ([tavily.com](https://tavily.com)) |
| `OPENWEATHER_API_KEY` | | Weather tool ([openweathermap.org](https://openweathermap.org/api)); new keys can take ~2 hours to activate |
| `SQLITE_DB_PATH` / `CHROMA_PERSIST_DIR` | | Storage locations (default `./data`) |
| `ROUTER_MODE` | | `hybrid` (default), `llm` (always function calling) or `classifier` |
| `HYBRID_CONFIDENCE_THRESHOLD` / `MAX_TOOL_ROUNDS` | | Classifier fast-path cut-off (0.8) and tool-loop limit (4) |
| `MEMORY_MODE` | | `llm` (extract facts, default) or `heuristic` (store raw messages) |
| `RATE_LIMIT_CHAT_PER_MINUTE` / `RATE_LIMIT_UPLOAD_PER_MINUTE` / `MAX_UPLOAD_MB` | | Abuse protection (defaults 20 / 5 / 10) |

### Tests and checks

```bash
ruff check src tests && pytest                                   # backend
cd frontend && npm run lint && npm run typecheck && npm test     # frontend
```

---

## ☁️ Deployment

`docker build .` produces one image: a Node stage builds the React app, and the Python stage serves it with the API.

- **Railway:** `railway.json` builds the Dockerfile and health-checks `/health`. Attach a volume at `/app/data`, or SQLite and ChromaDB data is lost on every redeploy.
- **Hugging Face Spaces** with Supabase persistence is planned in [#18](https://github.com/vid6848/ContextAI/issues/18) and [#19](https://github.com/vid6848/ContextAI/issues/19).
