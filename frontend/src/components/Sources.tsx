import { FileText, Globe } from "lucide-react"
import { useEffect, useRef } from "react"

import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { domainOf } from "@/lib/citations"
import type { Source } from "@/lib/types"
import { cn } from "@/lib/utils"
import { useCitations } from "@/store/citations"
import { useActiveMessages } from "@/store/chat"

function Favicon({ url }: { url: string }) {
  return (
    <img
      src={`https://icons.duckduckgo.com/ip3/${domainOf(url)}.ico`}
      alt=""
      className="size-4 shrink-0 rounded-sm"
      loading="lazy"
      onError={(e) => (e.currentTarget.style.visibility = "hidden")}
    />
  )
}

/** Web results as a row of cards above the answer, like a search engine's source strip. */
export function WebSourceStrip({ sources, messageKey }: { sources: Source[]; messageKey: string }) {
  const show = useCitations((s) => s.show)
  return (
    <ol className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label="Web sources">
      {sources.slice(0, 4).map((s) => (
        <li key={s.n}>
          <button
            type="button"
            onClick={() => show(messageKey, s.n)}
            className="flex h-full w-full flex-col justify-between gap-2 rounded-xl border bg-card p-2.5 text-left hover:border-ring/50"
          >
            <span className="line-clamp-2 text-[13px] leading-snug">{s.title}</span>
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Favicon url={s.url ?? ""} />
              <span className="truncate">{domainOf(s.url ?? "")}</span>
              <span className="ml-auto tabular-nums">{s.n}</span>
            </span>
          </button>
        </li>
      ))}
    </ol>
  )
}

/** Side panel listing every source of one answer, with the clicked citation highlighted. */
export function SourcesPanel() {
  const open = useCitations((s) => s.open)
  const close = useCitations((s) => s.close)
  const messages = useActiveMessages()
  const sources = (open && messages.find((m) => m.key === open.messageKey)?.meta?.sources) || []
  const activeRef = useRef<HTMLLIElement>(null)

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" })
  }, [open?.active, open?.messageKey])

  const web = sources[0]?.kind === "web"
  return (
    <Sheet open={!!open} onOpenChange={(o) => !o && close()}>
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-md">
        <SheetHeader className="border-b">
          <SheetTitle>Sources</SheetTitle>
          <SheetDescription>
            {web ? "Web pages this answer is based on." : "Passages from your documents this answer is based on."}
          </SheetDescription>
        </SheetHeader>
        <ol className="flex-1 space-y-3 overflow-y-auto p-4">
          {sources.map((s) => {
            const active = s.n === open?.active
            return (
              <li
                key={s.n}
                ref={active ? activeRef : undefined}
                className={cn("rounded-xl border bg-card p-3.5", active && "border-transparent ring-2 ring-step-docs/60", active && web && "ring-step-route/60")}
              >
                <div className="flex items-start gap-2.5">
                  <span
                    className={cn(
                      "mt-px flex h-5 min-w-5 items-center justify-center rounded-md px-1 text-xs font-medium tabular-nums",
                      web ? "bg-step-route/10 text-step-route" : "bg-step-docs/10 text-step-docs",
                    )}
                  >
                    {s.n}
                  </span>
                  {web ? (
                    <a href={s.url} target="_blank" rel="noreferrer noopener" className="min-w-0 flex-1 hover:underline">
                      <span className="block text-sm font-medium">{s.title}</span>
                      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <Globe className="size-3" /> {domainOf(s.url ?? "")}
                      </span>
                    </a>
                  ) : (
                    <div className="min-w-0 flex-1">
                      <span className="flex items-center gap-1.5 text-sm font-medium">
                        <FileText className="size-3.5 shrink-0 text-muted-foreground" />
                        <span className="truncate">{s.document}</span>
                      </span>
                      <span className="text-xs text-muted-foreground">Page {s.page}</span>
                    </div>
                  )}
                </div>
                {s.excerpt && (
                  <blockquote className="mt-2.5 border-l-2 pl-3 text-[13.5px] leading-relaxed whitespace-pre-line text-foreground/80">
                    {s.excerpt}
                  </blockquote>
                )}
              </li>
            )
          })}
        </ol>
      </SheetContent>
    </Sheet>
  )
}
