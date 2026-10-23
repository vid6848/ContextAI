import { FileText, RotateCcw } from "lucide-react"
import { useEffect, useState } from "react"

import { AgentTrace } from "@/components/AgentTrace"
import { Button } from "@/components/ui/button"
import type { AgentStep } from "@/lib/types"
import { cn } from "@/lib/utils"

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
export function DemoReplay({ onReplay }: { onReplay: () => void }) {
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
        <span className="mb-1.5 flex items-center gap-2 rounded-xl border bg-background py-1.5 pr-3 pl-2 text-[0.8125rem]">
          <span className="flex size-6 items-center justify-center rounded-md bg-step-docs/10 text-step-docs">
            <FileText className="size-3.5" />
          </span>
          northwind_q3.pdf
        </span>
        <p className="max-w-[85%] rounded-2xl rounded-br-md bg-secondary px-4 py-2.5 text-[1rem]">
          What are the main risks in this report? Keep it short.
        </p>
      </div>

      <div className="mt-6 min-h-[10.5rem]">
        <AgentTrace meta={{ steps }} streaming={thinking} defaultOpen />
        <p className="text-[1.0625rem] leading-relaxed" aria-live="polite">
          {TOKENS.slice(0, words).map((t, i) => {
            const cite = /^\[(\d)\]([.,]?)$/.exec(t)
            return cite ? (
              <span key={i}>
                <span className="mx-0.5 inline-flex h-[1.125rem] min-w-[1.125rem] -translate-y-px items-center justify-center rounded-md bg-step-docs/10 px-1 align-middle text-[0.6875rem] font-medium text-step-docs">
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
