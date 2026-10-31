import { Eye, EyeOff } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { Logo } from "@/components/Logo"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useAuth } from "@/lib/auth"

const MIN_PASSWORD = 8
const fieldClass = "h-12 w-full rounded-xl border bg-background px-4 text-[1rem] outline-none focus:border-brand/50"

function GoogleMark() {
  return (
    <svg viewBox="0 0 24 24" className="size-[1.1rem]" aria-hidden="true">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1Z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23Z" />
      <path fill="#FBBC05" d="M5.84 14.1A6.6 6.6 0 0 1 5.5 12c0-.73.13-1.44.34-2.1V7.07H2.18A11 11 0 0 0 1 12c0 1.78.43 3.45 1.18 4.93l3.66-2.84Z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15A10.5 10.5 0 0 0 12 1 11 11 0 0 0 2.18 7.07l3.66 2.84C6.71 7.3 9.14 5.38 12 5.38Z" />
    </svg>
  )
}

export function SignInDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { googleEnabled, signInWithGoogle, signIn, signUp } = useAuth()
  const [creating, setCreating] = useState(false)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const close = () => {
    onClose()
    setPassword("")
    setError(null)
    setNotice(null)
  }

  const switchMode = () => {
    setCreating(!creating)
    setError(null)
    setNotice(null)
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      if (creating) {
        const signedIn = await signUp(email.trim(), password)
        if (!signedIn) {
          setCreating(false)
          setNotice(`Almost there: confirm ${email.trim()} from your inbox, then sign in.`)
          return
        }
      } else {
        await signIn(email.trim(), password)
      }
      close()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Try again in a minute.")
    } finally {
      setBusy(false)
    }
  }

  const google = async () => {
    try {
      await signInWithGoogle() // redirects away to Google
    } catch {
      toast.error("Google sign-in isn't available right now. Use your email and password instead.")
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && close()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader className="items-center text-center">
          <Logo className="mb-2 size-9" />
          <DialogTitle className="font-display text-[1.6rem]">
            {creating ? "Create your account" : "Sign in to ContextAI"}
          </DialogTitle>
          <DialogDescription>
            Keep your chats, memories and documents across devices. Everything you did as a guest comes with you.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {googleEnabled && (
            <>
              <Button variant="outline" className="h-12 w-full gap-3 rounded-xl text-[1rem]" onClick={google}>
                <GoogleMark /> Continue with Google
              </Button>
              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                <span className="h-px flex-1 bg-border" /> or <span className="h-px flex-1 bg-border" />
              </div>
            </>
          )}

          <form onSubmit={submit} className="space-y-2.5">
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
              placeholder="Email"
              className={fieldClass}
            />
            <label htmlFor="signin-password" className="sr-only">
              Password
            </label>
            <div className="relative">
              <input
                id="signin-password"
                type={showPassword ? "text" : "password"}
                required
                minLength={creating ? MIN_PASSWORD : undefined}
                autoComplete={creating ? "new-password" : "current-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={creating ? `Password (at least ${MIN_PASSWORD} characters)` : "Password"}
                className={`${fieldClass} pr-12`}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                className="absolute top-1 right-1 flex size-10 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground"
              >
                {showPassword ? <EyeOff className="size-4.5" /> : <Eye className="size-4.5" />}
              </button>
            </div>
            {error && (
              <p role="alert" className="text-sm text-step-error">
                {error}
              </p>
            )}
            {notice && (
              <p role="status" className="text-sm text-step-docs">
                {notice}
              </p>
            )}
            <Button type="submit" className="h-12 w-full rounded-xl text-[1rem]" disabled={busy}>
              {busy ? "One moment…" : creating ? "Create account" : "Sign in"}
            </Button>
          </form>

          <p className="text-center text-sm text-muted-foreground">
            {creating ? "Already have an account?" : "New to ContextAI?"}{" "}
            <button type="button" onClick={switchMode} className="min-h-10 font-medium text-foreground underline underline-offset-2">
              {creating ? "Sign in" : "Create an account"}
            </button>
          </p>
        </div>
      </DialogContent>
    </Dialog>
  )
}
