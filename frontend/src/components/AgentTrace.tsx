import { ChevronRight } from "lucide-react"
import { useState } from "react"

import { formatDuration } from "@/lib/dates"
import type { AgentStep, MessageMeta } from "@/lib/types"
import { cn } from "@/lib/utils"

type StepKind = "memory" | "route" | "tool" | "docs" | "error"

function stepKind(step: AgentStep): StepKind {
  if (step.status === "error") return "error"
  if (step.id === "memory") return "memory"
  if (step.id === "intent") return "route"
  if (step.id === "tool:document_rag") return "docs"
  return "tool"
}

const NODE: Record<StepKind, string> = {
  memory: "bg-step-memory",
  route: "bg-step-route",
  tool: "bg-step-tool",
  docs: "bg-step-docs",
  error: "bg-step-error",
}

const RING: Record<StepKind, string> = {
  memory: "ring-step-memory/30",
  route: "ring-step-route/30",
  tool: "ring-step-tool/30",
  docs: "ring-step-docs/30",
  error: "ring-step-error/30",
}

/**
 * The agent's work for one answer, as a rail of colour-coded nodes. Open while the answer streams,
 * folded into a one-line summary afterwards; every finished step expands to show its input/output.
 */
export function AgentTrace({
  meta,
  streaming,
  defaultOpen = false,
}: {
  meta?: MessageMeta
  streaming?: boolean
  /** Stay expanded after streaming ends (the landing-page demo) instead of folding into the summary. */
  defaultOpen?: boolean
}) {
  const [userOpen, setUserOpen] = useState(defaultOpen)
  const steps = meta?.steps ?? []
  if (!steps.length && !streaming) return null

  const open = streaming || userOpen
  const running = steps.find((s) => s.status === "running")
  const total = steps.reduce((t, s) => t + (s.duration_ms ?? 0), 0)

  const summary = streaming
    ? running?.label ?? (steps.length ? "Writing the answer" : "Thinking")
    : `${steps.length} ${steps.length === 1 ? "step" : "steps"} in ${formatDuration(total)}`

  return (
    <div className="mb-3 text-[13.5px]">
      <button
        type="button"
        onClick={() => !streaming && setUserOpen((o) => !o)}
        aria-expanded={open}
        className={cn(
          "group inline-flex items-center gap-2 rounded-md py-1 pr-2 text-muted-foreground",
          !streaming && "hover:text-foreground",
        )}
      >
        {streaming ? (
          <span className="relative flex size-3.5 items-center justify-center">
            <span className="absolute size-3.5 animate-ping rounded-full bg-step-route/40" />
            <span className="size-2 rounded-full bg-step-route" />
          </span>
        ) : (
          <span className="flex items-center gap-[3px]" aria-hidden>
            {steps.map((s) => (
              <span key={s.id} className={cn("size-[7px] rounded-full", NODE[stepKind(s)])} />
            ))}
          </span>
        )}
        <span>{summary}</span>
        {!streaming && (
          <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} aria-hidden />
        )}
      </button>

      {open && steps.length > 0 && (
        <ol className="relative mt-1.5 ml-[6px] space-y-0.5 border-l border-border pl-4">
          {steps.map((step) => (
            <TraceStep key={step.id} step={step} />
          ))}
          {!streaming && meta?.intent && (
            <li className="pt-1 text-xs text-muted-foreground">
              Routed as {meta.intent.toLowerCase().replace("_", " ")}
              {typeof meta.confidence === "number" && ` with ${Math.round(meta.confidence * 100)}% confidence`}
            </li>
          )}
        </ol>
      )}
    </div>
  )
}

function TraceStep({ step }: { step: AgentStep }) {
  const [expanded, setExpanded] = useState(false)
  const kind = stepKind(step)
  const expandable = step.detail != null && step.status !== "running"

  return (
    <li className="relative">
      <span
        className={cn(
          "absolute top-[11px] -left-[21px] size-[9px] rounded-full ring-4",
          NODE[kind],
          RING[kind],
          step.status === "running" && "animate-pulse",
        )}
        aria-hidden
      />
      <button
        type="button"
        disabled={!expandable}
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expandable ? expanded : undefined}
        className={cn(
          "flex w-full items-baseline gap-3 rounded-md px-2 py-1 text-left",
          expandable ? "hover:bg-accent" : "cursor-default",
          kind === "error" ? "text-step-error" : "text-foreground/85",
        )}
      >
        <span className="flex-1">{step.label}</span>
        {step.status === "running" ? (
          <span className="text-xs text-muted-foreground">running</span>
        ) : (
          step.duration_ms != null && (
            <span className="font-mono text-xs tabular-nums text-muted-foreground">
              {formatDuration(step.duration_ms)}
            </span>
          )
        )}
      </button>
      {expanded && (
        <pre className="mt-1 mb-2 ml-2 max-h-72 overflow-auto rounded-lg border bg-card p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-muted-foreground">
          {JSON.stringify(step.detail, null, 2)}
        </pre>
      )}
    </li>
  )
}
