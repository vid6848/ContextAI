import { cn } from "@/lib/utils"

/**
 * The drifting violet/blue/teal light and dot grid shared by the landing hero and the chat, so the
 * app feels like the page you arrived from. "soft" keeps it quiet behind long-form reading.
 */
export function BrandBackground({ soft = false }: { soft?: boolean }) {
  return (
    <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden" aria-hidden>
      <div
        className={cn(
          "absolute -top-[20%] -left-[10%] size-[46rem] animate-drift rounded-full blur-[120px]",
          soft ? "bg-step-memory/15 dark:bg-step-memory/12" : "bg-step-memory/30",
        )}
      />
      <div
        className={cn(
          "absolute top-[10%] -right-[15%] size-[42rem] animate-drift rounded-full blur-[120px]",
          soft ? "bg-step-route/12 dark:bg-step-route/10" : "bg-step-route/25",
        )}
        style={{ animationDelay: "-7s" }}
      />
      <div
        className={cn(
          "absolute -bottom-[30%] left-[25%] size-[40rem] animate-drift rounded-full blur-[120px]",
          soft ? "bg-step-docs/12 dark:bg-step-docs/10" : "bg-step-docs/25",
        )}
        style={{ animationDelay: "-14s" }}
      />
      <div
        className={cn("absolute inset-0", soft ? "opacity-[0.18] dark:opacity-10" : "opacity-[0.35] dark:opacity-20")}
        style={{
          backgroundImage: "radial-gradient(var(--muted-foreground) 1px, transparent 1px)",
          backgroundSize: "28px 28px",
          maskImage: "radial-gradient(ellipse 70% 60% at 50% 45%, black 20%, transparent 75%)",
        }}
      />
    </div>
  )
}
