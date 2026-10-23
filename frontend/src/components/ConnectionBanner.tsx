import { CloudOff, ServerCrash } from "lucide-react"

import type { ConnectionState } from "@/hooks/useConnection"

export function ConnectionBanner({ state }: { state: ConnectionState }) {
  if (state === "online") return null
  const offline = state === "offline"
  return (
    <div role="status" className="mx-auto mb-2 flex w-full max-w-[720px] items-center gap-2.5 rounded-xl border border-step-tool/30 bg-step-tool/5 px-3.5 py-2 text-sm">
      {offline ? (
        <CloudOff className="size-4 shrink-0 text-step-tool" aria-hidden />
      ) : (
        <ServerCrash className="size-4 shrink-0 text-step-tool" aria-hidden />
      )}
      <span>
        {offline
          ? "You're offline. Reconnect to send messages."
          : "ContextAI's server isn't responding. Retrying every few seconds."}
      </span>
    </div>
  )
}
