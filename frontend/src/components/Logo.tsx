import { cn } from "@/lib/utils"

/** A three-node trace: the agent recalling, routing and acting, the same colours as the step rail. */
export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={cn("size-6", className)} aria-hidden="true">
      <path d="M8 5.5v13" stroke="currentColor" strokeOpacity={0.25} strokeWidth={2} strokeLinecap="round" />
      <path d="M8 18.5c0-3 2-4.5 5-4.5h3" fill="none" stroke="currentColor" strokeOpacity={0.25} strokeWidth={2} strokeLinecap="round" />
      <circle cx="8" cy="5.5" r="3" className="fill-step-memory" />
      <circle cx="8" cy="12" r="3" className="fill-step-route" />
      <circle cx="17.5" cy="14" r="3.5" className="fill-step-tool" />
    </svg>
  )
}
