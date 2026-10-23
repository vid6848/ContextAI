import { Brain, CloudSun, FileSearch, TrendingUp } from "lucide-react"

import { cn } from "@/lib/utils"

/* Each prompt shows off one capability, styled like the landing page's floating cards and tinted with the
   colour that kind of step gets in the trace. */
const PROMPTS = [
  { text: "What's the weather in Tokyo right now?", hint: "Live weather", icon: CloudSun, tint: "text-step-tool bg-step-tool/12" },
  { text: "Bitcoin and Ethereum prices, and how many ETH one BTC buys", hint: "Chains two tools", icon: TrendingUp, tint: "text-step-route bg-step-route/12" },
  { text: "Remember that I prefer answers with Python examples", hint: "Long-term memory", icon: Brain, tint: "text-step-memory bg-step-memory/12" },
  { text: "Summarize the PDF I uploaded", hint: "Reads your documents", icon: FileSearch, tint: "text-step-docs bg-step-docs/12" },
]

export function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="mx-auto flex w-full max-w-[var(--content-width)] flex-1 flex-col items-center justify-center px-4 pb-10 text-center">
      <h1
        className="animate-rise max-w-[16ch] font-display text-[clamp(2.5rem,4.6vw,4.25rem)] leading-[1.02] font-semibold tracking-[-0.04em]"
        style={{ animationDelay: "0.05s" }}
      >
        What can I <span className="text-gradient">help you with?</span>
      </h1>
      <p
        className="animate-rise mt-4 max-w-[50ch] text-[1.05rem] leading-relaxed text-muted-foreground"
        style={{ animationDelay: "0.15s" }}
      >
        Ask about anything. ContextAI checks live data, reads your PDFs, remembers what you tell it, and shows every
        step it takes.
      </p>
      <ul className="mt-10 grid w-full max-w-[52rem] gap-3 text-left sm:grid-cols-2">
        {PROMPTS.map((p, i) => (
          <li key={p.text} className="animate-rise" style={{ animationDelay: `${0.25 + i * 0.07}s` }}>
            <button
              type="button"
              onClick={() => onPick(p.text)}
              className="group flex h-full w-full items-start gap-3.5 rounded-2xl border text-left bg-card/80 p-4 shadow-[0_18px_40px_-28px_rgb(30_20_90/0.45)] backdrop-blur-xl transition-[transform,border-color] hover:-translate-y-0.5 hover:border-brand/40"
            >
              <span className={cn("flex size-10 shrink-0 items-center justify-center rounded-xl", p.tint)}>
                <p.icon className="size-5" />
              </span>
              <span>
                <span className="block text-[0.98rem] leading-snug font-medium">{p.text}</span>
                <span className="mt-1 block text-[0.85rem] text-muted-foreground">{p.hint}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
