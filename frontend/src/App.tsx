import { Menu, PanelLeftOpen, SquarePen } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { Outlet, useLocation, useNavigate } from "react-router"
import { toast } from "sonner"

import { AppSidebar, type Panel } from "@/components/AppSidebar"
import { BrandBackground } from "@/components/BrandBackground"
import { Panels } from "@/components/Panels"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet"
import { useReminderNotifications } from "@/hooks/useReminderNotifications"
import { onIdentityChange, useAuth } from "@/lib/auth"
import { useChat } from "@/store/chat"

const COLLAPSED_KEY = "contextai_sidebar_collapsed"

export function AppLayout() {
  const loadConversations = useChat((s) => s.loadConversations)
  useReminderNotifications()
  const chatTitle = useChat((s) => s.conversations.find((c) => c.id === s.activeId)?.title)
  const { pathname } = useLocation()
  const title = pathname.startsWith("/c/") ? chatTitle : pathname === "/memory" ? "Memory" : undefined
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [panel, setPanel] = useState<Panel | null>(null)
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(COLLAPSED_KEY) === "1"
    } catch {
      return false
    }
  })

  useEffect(() => {
    void loadConversations()
  }, [loadConversations])

  // Signing in or out changes whose chats we show
  const reset = useChat((s) => s.reset)
  useEffect(
    () =>
      onIdentityChange((event, moved) => {
        reset()
        void loadConversations()
        navigate("/chat")
        if (event === "signed-in") toast.success(moved ? "Signed in. Your guest chats are in your account." : "Signed in")
        else toast("Signed out")
      }),
    [reset, loadConversations, navigate],
  )
  const { ready: authReady, required: authRequired, session } = useAuth()
  const mustSignIn = authReady && authRequired && !session



  const setCollapsedPersist = (value: boolean) => {
    setCollapsed(value)
    try {
      localStorage.setItem(COLLAPSED_KEY, value ? "1" : "0")
    } catch {
      /* non-essential */
    }
  }

  // Global shortcuts: ⌘/Ctrl+K search, ⌘/Ctrl+Shift+O new chat, ⌘/Ctrl+/ shortcut list
  const searchRef = useRef<HTMLInputElement>(null)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return
      const key = e.key.toLowerCase()
      if (key === "k") {
        e.preventDefault()
        if (window.matchMedia("(max-width: 767px)").matches) setMobileOpen(true)
        else setCollapsedPersist(false)
        setTimeout(() => searchRef.current?.focus(), 50)
      } else if (key === "o" && e.shiftKey) {
        e.preventDefault()
        navigate("/chat")
      } else if (key === "/") {
        e.preventDefault()
        setPanel("shortcuts")
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  })

  const openPanel = (p: Panel) => {
    setMobileOpen(false)
    setPanel(p)
  }

  return (
    <div className="relative isolate flex h-dvh overflow-hidden">
      <BrandBackground soft />
      <a
        href="#composer"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-lg focus:bg-primary focus:px-3 focus:py-2 focus:text-sm focus:text-primary-foreground"
      >
        Skip to message box
      </a>
      {!collapsed && (
        <aside className="hidden w-[17rem] shrink-0 border-r border-sidebar-border/70 md:block">
          <AppSidebar onCollapse={() => setCollapsedPersist(true)} onOpenPanel={openPanel} searchRef={searchRef} />
        </aside>
      )}

      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="w-[18rem] p-0" showCloseButton={false}>
          <SheetTitle className="sr-only">Chats</SheetTitle>
          <AppSidebar onNavigate={() => setMobileOpen(false)} onOpenPanel={openPanel} searchRef={searchRef} />
        </SheetContent>
      </Sheet>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-1 px-3">
          <Button variant="ghost" size="icon" className="md:hidden" onClick={() => setMobileOpen(true)} aria-label="Open sidebar">
            <Menu className="size-[1.125rem]" />
          </Button>
          {collapsed && (
            <>
              <Button
                variant="ghost"
                size="icon"
                className="hidden md:inline-flex"
                onClick={() => setCollapsedPersist(false)}
                aria-label="Open sidebar"
              >
                <PanelLeftOpen className="size-[1.125rem]" />
              </Button>
              <Button variant="ghost" size="icon" className="hidden md:inline-flex" onClick={() => navigate("/chat")} aria-label="New chat">
                <SquarePen className="size-[1.125rem]" />
              </Button>
            </>
          )}
          <h1 className="truncate px-2 text-[0.9rem] font-medium text-foreground/80">{title ?? ""}</h1>
          <Button variant="ghost" size="icon" className="ml-auto md:hidden" onClick={() => navigate("/chat")} aria-label="New chat">
            <SquarePen className="size-[1.125rem]" />
          </Button>
        </header>
        <Outlet />
      </main>

      <Panels open={mustSignIn ? "signin" : panel} onClose={() => setPanel(null)} />
    </div>
  )
}
