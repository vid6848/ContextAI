import { FileText, RotateCcw } from "lucide-react"
import { useEffect, useState } from "react"
import { Link } from "react-router"

import { AgentTrace } from "@/components/AgentTrace"
import { Logo } from "@/components/Logo"
import { Button } from "@/components/ui/button"
import type { AgentStep } from "@/lib/types"
import { cn } from "@/lib/utils"

export const WELCOMED_KEY = "contextai_welcomed"

// lucide no longer ships brand marks, so the GitHub logo is inlined
function GitHubMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" className={className} aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  )
}
const REPO_URL = "https://github.com/vid6848/ContextAI"

const ANSWER = "Two risks stand out: supplier delays [1] and cloud costs, which rose 12% this quarter [1]. Revenue still grew 18% on the new subscription tier [2]."

type Event = { at: number; step?: AgentStep }
const SCRIPT: Event[] = [
  { at: 300, step: { id: "memory", label: "Recalling memory", status: "running" } },
  { at: 800, step: { id: "memory", label: "Recalled 1 long-term memory", status: "done", duration_ms: 41 } },
  { at: 1000, step: { id: "intent", label: "Classifying intent", status: "running" } },
  { at: 1200, step: { id: "intent", label: "Routed to your attached file", status: "done", duration_ms: 1 } },
  { at: 1400, step: { id: "tool:document_rag", label: "Searching your documents", status: "running" } },
  { at: 2200, step: { id: "tool:document_rag", label: "Found 2 relevant passages", status: "done", duration_ms: 86 } },
]
const TOKENS_START = 2500
const TOKEN_MS = 45

function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches
}

const TOKENS = ANSWER.split(" ")
const FINAL_STEPS = SCRIPT.flatMap((e) => (e.step?.status === "done" ? [e.step] : []))

/** Replays one real interaction so visitors see the agent work before they try it. Remount to replay. */
function DemoReplay({ onReplay }: { onReplay: () => void }) {
  const [reduced] = useState(prefersReducedMotion)
  const [steps, setSteps] = useState<AgentStep[]>(() => (reduced ? FINAL_STEPS : []))
  const [words, setWords] = useState(() => (reduced ? TOKENS.length : 0))
  const done = words >= TOKENS.length

  useEffect(() => {
    if (reduced) return
    const timers = SCRIPT.map((e) =>
      setTimeout(() => {
        setSteps((prev) => {
          const i = prev.findIndex((s) => s.id === e.step!.id)
          return i < 0 ? [...prev, e.step!] : prev.map((s, j) => (j === i ? e.step! : s))
        })
      }, e.at),
    )
    TOKENS.forEach((_, i) => timers.push(setTimeout(() => setWords(i + 1), TOKENS_START + i * TOKEN_MS)))
    return () => timers.forEach(clearTimeout)
  }, [reduced])

  const thinking = words === 0
  return (
    <div className="rounded-3xl border bg-card p-5 shadow-[0_1px_2px_rgb(0_0_0/0.04),0_24px_48px_-24px_rgb(0_0_0/0.18)] sm:p-6">
      <div className="flex flex-col items-end">
        <span className="mb-1.5 flex items-center gap-2 rounded-xl border bg-background py-1.5 pr-3 pl-2 text-[13px]">
          <span className="flex size-6 items-center justify-center rounded-md bg-step-docs/10 text-step-docs">
            <FileText className="size-3.5" />
          </span>
          northwind_q3.pdf
        </span>
        <p className="max-w-[85%] rounded-2xl rounded-br-md bg-secondary px-4 py-2.5 text-[15px]">
          What are the main risks in this report? Keep it short.
        </p>
      </div>

      <div className="mt-6 min-h-[168px]">
        <AgentTrace meta={{ steps }} streaming={thinking} defaultOpen />
        <p className="text-[15.5px] leading-relaxed" aria-live="polite">
          {TOKENS.slice(0, words).map((t, i) => {
            const cite = /^\[(\d)\]([.,]?)$/.exec(t)
            return cite ? (
              <span key={i}>
                <span className="mx-0.5 inline-flex h-[18px] min-w-[18px] -translate-y-px items-center justify-center rounded-md bg-step-docs/10 px-1 align-middle text-[11px] font-medium text-step-docs">
                  {cite[1]}
                </span>
                {cite[2]}{" "}
              </span>
            ) : (
              <span key={i}>{t} </span>
            )
          })}
          {!thinking && !done && <span className="stream-caret" />}
        </p>
      </div>

      <div className={cn("mt-3 flex justify-end transition-opacity", done ? "opacity-100" : "opacity-0")}>
        <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={onReplay} disabled={!done}>
          <RotateCcw className="size-3.5" /> Replay
        </Button>
      </div>
    </div>
  )
}

const CAPABILITIES = [
  {
    dot: "bg-step-memory",
    title: "Remembers what matters",
    body: "Tell it once that you prefer short answers or live in Pune. It recalls that in later chats, and you can clear it any time.",
  },
  {
    dot: "bg-step-tool",
    title: "Checks live data",
    body: "Weather, crypto prices, web search and a calculator, picked automatically and shown as a step you can open and inspect.",
  },
  {
    dot: "bg-step-docs",
    title: "Reads your PDFs",
    body: "Drop in a report or a lease and ask about it. Answers cite the exact passage and page, one click away.",
  },
]

function WelcomePage() {
  const [replay, setReplay] = useState(0)
  const markWelcomed = () => {
    try {
      localStorage.setItem(WELCOMED_KEY, "1")
    } catch {
      /* non-essential */
    }
  }

  return (
    <div className="min-h-dvh overflow-y-auto">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5 sm:px-8">
        <span className="flex items-center gap-2">
          <Logo className="size-6" />
          <span className="text-[16px] font-semibold tracking-[-0.01em]">ContextAI</span>
        </span>
        <Button asChild variant="ghost" size="sm" className="text-muted-foreground">
          <a href={REPO_URL} target="_blank" rel="noreferrer noopener">
            <GitHubMark className="size-4" /> Source
          </a>
        </Button>
      </header>

      <main className="mx-auto grid max-w-6xl items-center gap-12 px-5 pt-8 pb-20 sm:px-8 lg:grid-cols-[1fr_1.05fr] lg:gap-16 lg:pt-16">
        <section>
          <h1 className="max-w-[14ch] text-[44px] leading-[1.05] font-medium tracking-[-0.03em] sm:text-[56px]">
            An assistant that shows its work.
          </h1>
          <p className="mt-6 max-w-[46ch] text-[17px] leading-relaxed text-muted-foreground">
            ContextAI remembers what you tell it, checks live data, and reads your PDFs. Every answer comes with the
            steps it took and the sources it used.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild size="lg" className="h-11 rounded-full px-6 text-[15px]">
              <Link to="/" onClick={markWelcomed}>
                Start chatting
              </Link>
            </Button>
            <Button asChild variant="outline" size="lg" className="h-11 rounded-full px-6 text-[15px]">
              <a href={REPO_URL} target="_blank" rel="noreferrer noopener">
                Read the code
              </a>
            </Button>
          </div>
          <p className="mt-4 text-sm text-muted-foreground">No sign-up needed. Your chats stay private to this browser.</p>
        </section>

        <DemoReplay key={replay} onReplay={() => setReplay((r) => r + 1)} />
      </main>

      <section className="border-t bg-sidebar/60">
        <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8">
          <ol className="relative grid gap-10 border-l pl-8 md:grid-cols-3 md:border-l-0 md:pl-0">
            {CAPABILITIES.map((c) => (
              <li key={c.title} className="relative md:border-t md:pt-6">
                <span
                  className={cn("absolute top-1.5 -left-[37px] size-[10px] rounded-full md:-top-[5px] md:left-0", c.dot)}
                  aria-hidden
                />
                <h2 className="text-[17px] font-medium">{c.title}</h2>
                <p className="mt-2 max-w-[38ch] leading-relaxed text-muted-foreground">{c.body}</p>
              </li>
            ))}
          </ol>
          <p className="mt-14 text-sm text-muted-foreground">
            Built with FastAPI, LangGraph, Gemini via LiteLLM, ChromaDB, React and Tailwind.{" "}
            <a href={REPO_URL} className="underline underline-offset-2 hover:text-foreground" target="_blank" rel="noreferrer noopener">
              See how it works
            </a>
            .
          </p>
        </div>
      </section>
    </div>
  )
}

export default WelcomePage
