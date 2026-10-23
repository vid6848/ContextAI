# ContextAI 🤖

ContextAI is an agentic personal AI assistant. A LangGraph pipeline sits behind a FastAPI backend and combines conversation memory, semantic long-term memory, live tools (web search, weather, crypto, calculator), PDF question answering (RAG) and reminders.

> 🚧 **ContextAI is being upgraded from a prototype into a production-grade chat assistant.** See the [Roadmap](#-roadmap) below. Every change is tracked as a GitHub issue and lands through a pull request.

---

## ✨ Features

| Area | What it does |
|---|---|
| **Agent orchestration** | LangGraph state machine: recall memory → classify intent → route to a tool or RAG → generate a response → save memory |
| **Intent routing** | TF-IDF + Logistic Regression classifier picks the tool path |
| **Live tools** | Tavily web search, OpenWeather, CoinGecko crypto prices, and a safe AST-based calculator |
| **Document RAG** | PDF ingestion with PyMuPDF, chunking, ChromaDB retrieval, and answers with page citations |
| **Memory** | SQLite short-term conversation history and ChromaDB semantic long-term memory |
| **Reminders** | Create, complete and delete reminders, with due-reminder banners |
| **LLM layer** | LiteLLM (provider-agnostic, Gemini by default) with bounded retries and fallback model |

---

## 🛠 Tech Stack

**Current:** FastAPI · LangGraph · LiteLLM (Gemini) · SQLite · ChromaDB · scikit-learn · PyMuPDF · vanilla JS frontend · Docker · pytest

**Target, after the roadmap:**

| Layer | Choice | Why |
|---|---|---|
| Frontend | React + Vite + TypeScript + Tailwind + shadcn/ui | Component-based, typed, and polished UI primitives |
| API | FastAPI + Server-Sent Events | Token streaming and live agent-step events |
| Agent | LangGraph + LLM function calling (hybrid with the classifier) | Multi-tool chaining, measured against the classifier baseline |
| LLM | Gemini via LiteLLM (swap to Claude or Groq with one env var) | Free tier, streaming, and function calling |
| Data | Supabase Postgres + pgvector (SQLite/Chroma for local dev) | Persistence that survives free-host restarts |
| Auth | Supabase Auth (Google) + guest mode | Real per-user isolation |
| Observability | Langfuse | Traces, token cost, latency and feedback |
| Hosting | Hugging Face Spaces (Docker) | Free, 16 GB RAM, no credit expiry |
| CI | GitHub Actions: ruff, pytest, eval suite | Automated quality checks |

---

## 🗺 Roadmap

Progress is tracked with [milestones](https://github.com/vid6848/ContextAI/milestones) and [issues](https://github.com/vid6848/ContextAI/issues). Each phase is delivered through pull requests that reference these issues.

### Phase 1: Foundation & hardening
Make the backend behave like a real chat service and close the security gaps.
- [#1](https://github.com/vid6848/ContextAI/issues/1) Server-side conversations with per-conversation history. This fixes "New chat" leaking context from older chats.
- [#2](https://github.com/vid6848/ContextAI/issues/2) Streaming chat endpoint (SSE) with live agent-step events
- [#3](https://github.com/vid6848/ContextAI/issues/3) Stop generation, regenerate, and edit-and-resend
- [#4](https://github.com/vid6848/ContextAI/issues/4) Security: per-user isolation, rate limits, upload limits, and safe errors
- [#5](https://github.com/vid6848/ContextAI/issues/5) Repo hygiene: pinned deps, slim Docker image, remove Streamlit, CI

### Phase 2: Frontend rebuild
A ChatGPT/Claude-class interface.
- [#6](https://github.com/vid6848/ContextAI/issues/6) React + Vite + TS + Tailwind + shadcn/ui foundation
- [#7](https://github.com/vid6848/ContextAI/issues/7) App shell, grouped sidebar, auto-titles, and light/dark mode
- [#8](https://github.com/vid6848/ContextAI/issues/8) Streaming messages with a collapsible agent-step timeline
- [#9](https://github.com/vid6848/ContextAI/issues/9) Code highlighting, tables, math, and message actions (copy, regenerate, edit, feedback)
- [#10](https://github.com/vid6848/ContextAI/issues/10) Composer with drag-and-drop PDF attachments
- [#11](https://github.com/vid6848/ContextAI/issues/11) Inline citations panel, plus weather and crypto result cards
- [#12](https://github.com/vid6848/ContextAI/issues/12) Shortcuts, mobile layout, error states, and landing page

### Phase 3: Smarter agent
- [#13](https://github.com/vid6848/ContextAI/issues/13) LLM function calling with multi-tool chaining (hybrid router)
- [#14](https://github.com/vid6848/ContextAI/issues/14) RAG upgrade: structure-aware chunking, re-ranking, and grounded answers
- [#15](https://github.com/vid6848/ContextAI/issues/15) LLM-extracted long-term memory, with a Memory page
- [#16](https://github.com/vid6848/ContextAI/issues/16) Natural-language reminders with notifications

### Phase 4: Accounts, persistence & deploy
- [#17](https://github.com/vid6848/ContextAI/issues/17) Supabase Auth (Google) + guest mode
- [#18](https://github.com/vid6848/ContextAI/issues/18) Supabase Postgres + pgvector persistence
- [#19](https://github.com/vid6848/ContextAI/issues/19) Deploy to Hugging Face Spaces

### Phase 5: Evals, observability & showcase
- [#20](https://github.com/vid6848/ContextAI/issues/20) Automated evaluation suite in CI (routing accuracy, RAG faithfulness, latency)
- [#21](https://github.com/vid6848/ContextAI/issues/21) Langfuse tracing
- [#22](https://github.com/vid6848/ContextAI/issues/22) Demo GIF, architecture diagram, and design decisions

---

## 📁 Project Structure

```text
ContextAI/
├── src/
│   ├── backend/
│   │   ├── agent/          # LangGraph graph + state
│   │   ├── api/            # FastAPI routes
│   │   ├── classifier/     # TF-IDF + Logistic Regression intent classifier
│   │   ├── core/           # Settings (pydantic-settings)
│   │   ├── llm/            # LiteLLM client with retry + fallback
│   │   ├── memory/         # SQLite history + ChromaDB semantic memory
│   │   ├── rag/            # PDF ingestion + retrieval
│   │   ├── reminders/      # Reminder manager
│   │   ├── tools/          # Calculator, weather, crypto, web search
│   │   └── main.py         # FastAPI app; also serves the web UI
│   └── frontend/web/       # Web UI (index.html, app.js, styles.css)
├── tests/                  # pytest suite
├── Dockerfile              # Production image
└── railway.json            # Railway deployment config
```

---

## 🚀 Getting Started

**Prerequisites:** Python 3.11+

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then add your GEMINI_API_KEY (and optional tool keys)
uvicorn src.backend.main:app --reload --port 8000
```

Open http://localhost:8000 for the chat UI and http://localhost:8000/docs for the API docs.

### Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | ✅ | LLM access ([Google AI Studio](https://aistudio.google.com/)) |
| `MODEL_NAME` / `FALLBACK_MODEL_NAME` | | Any LiteLLM model string |
| `TAVILY_API_KEY` | | Web search tool |
| `OPENWEATHER_API_KEY` | | Weather tool |
| `SQLITE_DB_PATH` / `CHROMA_PERSIST_DIR` | | Storage locations (default `./data`) |

### Tests

```bash
pytest
```

---

## ☁️ Deployment

The app runs as a single Docker container: FastAPI serves both the API and the UI.

- **Railway:** `railway.json` builds the `Dockerfile`. Attach a volume at `/app/data`, or SQLite and ChromaDB data is lost on every redeploy.
- **Hugging Face Spaces:** planned in [#19](https://github.com/vid6848/ContextAI/issues/19), together with Supabase persistence in [#18](https://github.com/vid6848/ContextAI/issues/18).
