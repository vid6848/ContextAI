# ContextAI

**An AI assistant that shows its work.** ContextAI remembers what you tell it, checks live data, and reads your PDFs. Every answer streams in alongside the steps the agent took (memory recall, routing, tool calls, document search) and the sources it used.

> 🚧 ContextAI is being built in public as a [5-phase roadmap](#-roadmap). Every change is tracked as an issue and lands through a pull request.

---

## ✨ Features

| | |
|---|---|
| **Live agent trace** | Each answer opens with a colour-coded rail of the agent's steps: violet memory, blue routing, amber tools, teal documents, red errors. Each step is timed, and you can expand it to see the exact tool input and output. |
| **Streaming chat** | Answers stream token by token over Server-Sent Events, with Stop (Esc), Regenerate, Edit-and-resend, Copy and 👍/👎 feedback. |
| **PDF Q&A with citations** | Drag a PDF into the chat and ask about it. Answers cite passages inline as `[1]`, and clicking one opens the exact excerpt and page. Documents are private to their owner. |
| **Live tools** | CoinGecko crypto prices and OpenWeather (shown as cards), Tavily web search (with source cards), and a safe AST-based calculator. |
| **Memory** | Per-conversation history in SQLite, plus long-term semantic memory in ChromaDB that carries useful facts across chats. |
| **Chat app** | Server-side conversations with LLM-written titles, a grouped sidebar with search, rename and delete, light/dark mode, keyboard shortcuts, mobile layout, and a landing page. |
| **Rich answers** | Syntax-highlighted code with copy, KaTeX math (prices stay prices), and GFM tables. |
| **Hardening** | Per-browser user isolation, rate limits, streamed upload size caps, PDF validation, and errors that never leak keys or internals. |

---

## 🧱 Architecture

```text
React SPA (Vite, TS, Tailwind, shadcn/ui, Zustand)
   │  REST + Server-Sent Events  (/api/v1/chat/stream: meta → step* → token* → done → title)
   ▼
FastAPI ──────────────────────────────── serves the built SPA on the same origin
   │
   ▼
LangGraph agent
   retrieve_memory ─▶ classify_intent ─┬─▶ calculator / weather / crypto / web_search ─┐
   (SQLite + Chroma)  (TF-IDF + LR, or  ├─▶ document_rag (Chroma, per-user, numbered)  ─┼─▶ generate_response ─▶ save_memory
                       attachments)     └──────────────────────────────────────────────┘   (LiteLLM → Gemini,
                                                                                            streamed, cancellable)
```

Every node runs inside a timed `agent_step` that streams `running → done/error` events through LangGraph's stream writer. The same graph serves the streaming and the plain JSON endpoint.

## 🛠 Tech Stack

| Layer | Now | Planned |
|---|---|---|
| Frontend | React 19, TypeScript, Vite, Tailwind v4, shadcn/ui, Zustand, React Router | |
| API | FastAPI + Server-Sent Events | |
| Agent | LangGraph, TF-IDF + Logistic Regression router | LLM function calling with multi-tool chaining ([#13](https://github.com/vid6848/ContextAI/issues/13)) |
| LLM | Gemini via LiteLLM (swap providers with one env var) | |
| Data | SQLite + ChromaDB | Supabase Postgres + pgvector ([#18](https://github.com/vid6848/ContextAI/issues/18)) |
| Auth | Anonymous per-browser id | Supabase Auth with Google ([#17](https://github.com/vid6848/ContextAI/issues/17)) |
| Quality | pytest (109), Vitest, ruff, oxlint, GitHub Actions | Eval suite ([#20](https://github.com/vid6848/ContextAI/issues/20)), Langfuse ([#21](https://github.com/vid6848/ContextAI/issues/21)) |
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

### Phase 3: Smarter agent
- [ ] [#13](https://github.com/vid6848/ContextAI/issues/13) LLM function calling with multi-tool chaining (hybrid router)
- [ ] [#14](https://github.com/vid6848/ContextAI/issues/14) RAG upgrade: structure-aware chunking, re-ranking, document management
- [ ] [#15](https://github.com/vid6848/ContextAI/issues/15) LLM-extracted long-term memory, with a Memory page
- [ ] [#16](https://github.com/vid6848/ContextAI/issues/16) Natural-language reminders with notifications

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
