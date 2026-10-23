import { cn } from "@/lib/utils"

/* Each prompt shows off one capability; its dot uses the same colour that step gets in the trace. */
const PROMPTS = [
  { text: "What's the weather in Tokyo right now?", dot: "bg-step-tool" },
  { text: "How much has Bitcoin moved in the last 24 hours?", dot: "bg-step-tool" },
  { text: "Remember that I prefer answers with Python examples", dot: "bg-step-memory" },
  { text: "Summarize the PDF I uploaded", dot: "bg-step-docs" },
]

export function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="mx-auto flex w-full max-w-[var(--content-width)] flex-1 flex-col justify-center px-4 pb-8">
      <h1 className="text-[2.125rem] font-medium tracking-[-0.015em]">What can I help with?</h1>
      <p className="mt-2 max-w-[52ch] text-muted-foreground">
        ContextAI remembers what you tell it, checks live data, and reads your PDFs. Every answer shows the steps it
        took.
      </p>
      <ul className="mt-8 divide-y border-y">
        {PROMPTS.map((p) => (
          <li key={p.text}>
            <button
              type="button"
              onClick={() => onPick(p.text)}
              className="flex w-full items-center gap-3 py-3 text-left text-[0.9375rem] text-foreground/85 transition-colors hover:text-foreground"
            >
              <span className={cn("size-2 shrink-0 rounded-full", p.dot)} aria-hidden />
              {p.text}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
