import { ArrowUp, Square } from "lucide-react"
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export interface ComposerHandle {
  focus: () => void
  setValue: (value: string) => void
}

interface ComposerProps {
  streaming: boolean
  onSend: (text: string) => void
  onStop: () => void
}

export const Composer = forwardRef<ComposerHandle, ComposerProps>(function Composer({ streaming, onSend, onStop }, ref) {
  const [value, setValue] = useState("")
  const textarea = useRef<HTMLTextAreaElement>(null)

  useImperativeHandle(ref, () => ({
    focus: () => textarea.current?.focus(),
    setValue: (v) => {
      setValue(v)
      requestAnimationFrame(() => textarea.current?.focus())
    },
  }))

  // Grow with the content up to ~8 lines, then scroll
  useEffect(() => {
    const el = textarea.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`
  }, [value])

  const submit = () => {
    if (streaming || !value.trim()) return
    onSend(value)
    setValue("")
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (streaming) onStop()
        else submit()
      }}
      className="relative flex items-end gap-2 rounded-3xl border bg-card p-2 pl-4 shadow-[0_1px_2px_rgb(0_0_0/0.04),0_4px_16px_-6px_rgb(0_0_0/0.08)] focus-within:border-ring/60"
    >
      <label htmlFor="composer" className="sr-only">
        Message ContextAI
      </label>
      <textarea
        id="composer"
        ref={textarea}
        rows={1}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault()
            submit()
          }
        }}
        placeholder="Ask anything, or ask about your documents"
        className="max-h-[220px] flex-1 resize-none bg-transparent py-2 text-[15.5px] leading-relaxed outline-none placeholder:text-muted-foreground"
      />
      <Button
        type="submit"
        size="icon"
        disabled={!streaming && !value.trim()}
        aria-label={streaming ? "Stop generating" : "Send message"}
        title={streaming ? "Stop (Esc)" : "Send (Enter)"}
        className={cn("size-9 shrink-0 rounded-full", streaming && "bg-foreground")}
      >
        {streaming ? <Square className="size-3.5 fill-current" /> : <ArrowUp className="size-4.5" />}
      </Button>
    </form>
  )
})
