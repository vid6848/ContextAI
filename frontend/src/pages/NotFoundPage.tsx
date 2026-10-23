import { Link } from "react-router"

import { Logo } from "@/components/Logo"
import { Button } from "@/components/ui/button"

export function NotFoundPage() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
      <Logo className="size-9" />
      <h1 className="text-2xl font-medium">This page doesn't exist</h1>
      <p className="max-w-[40ch] text-muted-foreground">The link may be broken, or the chat was deleted.</p>
      <Button asChild className="mt-2 rounded-full px-5">
        <Link to="/">Go to chats</Link>
      </Button>
    </main>
  )
}
