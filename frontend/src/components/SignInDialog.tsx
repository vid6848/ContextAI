import { Mail } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { Logo } from "@/components/Logo"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useAuth } from "@/lib/auth"

export function SignInDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { sendMagicLink } = useAuth()
  const [email, setEmail] = useState("")
  const [sentTo, setSentTo] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const sendLink = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim()) return
    setBusy(true)
    try {
      await sendMagicLink(email.trim())
      setSentTo(email.trim())
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't send the link. Try again in a minute.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) {
          onClose()
          setSentTo(null)
        }
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader className="items-center text-center">
          <Logo className="mb-2 size-9" />
          <DialogTitle className="font-display text-[1.6rem]">Sign in to ContextAI</DialogTitle>
          <DialogDescription>
            Keep your chats, memories and documents across devices. Everything you did as a guest comes with you.
          </DialogDescription>
        </DialogHeader>

        {sentTo ? (
          <div className="rounded-2xl border bg-step-docs/[0.06] p-5 text-center">
            <Mail className="mx-auto size-7 text-step-docs" />
            <p className="mt-3 font-medium">Check your inbox</p>
            <p className="mt-1 text-sm text-muted-foreground">
              We sent a sign-in link to {sentTo}. Open it on this device to finish signing in.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <form onSubmit={sendLink} className="space-y-2.5">
              <label htmlFor="signin-email" className="sr-only">
                Email
              </label>
              <input
                id="signin-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="h-12 w-full rounded-xl border bg-background px-4 text-[1rem] outline-none focus:border-brand/50"
              />
              <Button type="submit" className="h-12 w-full rounded-xl text-[1rem]" disabled={busy || !email.trim()}>
                {busy ? "Sending…" : "Email me a sign-in link"}
              </Button>
            </form>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
