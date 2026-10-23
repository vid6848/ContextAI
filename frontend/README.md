# ContextAI web app

React 19 + TypeScript + Vite + Tailwind CSS v4 + shadcn/ui (Radix). State lives in a small Zustand store
(`src/store/chat.ts`); the backend is reached through a typed client (`src/lib/api.ts`) that consumes the
`/api/v1/chat/stream` Server-Sent Events.

## Develop

Run the API and the Vite dev server side by side:

```bash
# terminal 1 — repo root
uvicorn src.backend.main:app --reload --port 8000

# terminal 2 — frontend/
npm install
npm run dev          # http://localhost:5173, proxies /api to :8000
```

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Dev server with hot reload |
| `npm run build` | Typecheck and build to `dist/` (FastAPI serves it at `/`) |
| `npm test` | Unit tests (Vitest) |
| `npm run lint` | Oxlint |
| `npm run typecheck` | `tsc -b` |

## Design notes

- One family (IBM Plex Sans, Plex Mono for code and tool I/O), neutral ink-on-paper palette, light and dark.
- The only colour is in the agent trace and encodes the step type: violet memory, blue routing,
  amber tools, teal documents, red errors. The logo and empty-state prompts reuse the same code.
