import { Menu, PanelLeftOpen, SquarePen } from "lucide-react"
import { useEffect, useState } from "react"
import { Outlet, useNavigate } from "react-router"

import { AppSidebar, type Panel } from "@/components/AppSidebar"
import { Panels } from "@/components/Panels"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet"
import { useChat } from "@/store/chat"

const COLLAPSED_KEY = "contextai_sidebar_collapsed"

export function AppLayout() {
  const loadConversations = useChat((s) => s.loadConversations)
  const title = useChat((s) => s.conversations.find((c) => c.id === s.activeId)?.title)
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

  const setCollapsedPersist = (value: boolean) => {
    setCollapsed(value)
    try {
      localStorage.setItem(COLLAPSED_KEY, value ? "1" : "0")
    } catch {
      /* non-essential */
    }
  }

  const openPanel = (p: Panel) => {
    setMobileOpen(false)
    setPanel(p)
  }

  return (
    <div className="flex h-dvh overflow-hidden">
      {!collapsed && (
        <aside className="hidden w-[260px] shrink-0 border-r border-sidebar-border md:block">
          <AppSidebar onCollapse={() => setCollapsedPersist(true)} onOpenPanel={openPanel} />
        </aside>
      )}

      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="w-[280px] p-0" showCloseButton={false}>
          <SheetTitle className="sr-only">Chats</SheetTitle>
          <AppSidebar onNavigate={() => setMobileOpen(false)} onOpenPanel={openPanel} />
        </SheetContent>
      </Sheet>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-1 px-2">
          <Button variant="ghost" size="icon" className="md:hidden" onClick={() => setMobileOpen(true)} aria-label="Open sidebar">
            <Menu className="size-[18px]" />
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
                <PanelLeftOpen className="size-[18px]" />
              </Button>
              <Button variant="ghost" size="icon" className="hidden md:inline-flex" onClick={() => navigate("/")} aria-label="New chat">
                <SquarePen className="size-[18px]" />
              </Button>
            </>
          )}
          <h1 className="truncate px-2 text-[14px] font-medium text-foreground/80">{title ?? ""}</h1>
          <Button variant="ghost" size="icon" className="ml-auto md:hidden" onClick={() => navigate("/")} aria-label="New chat">
            <SquarePen className="size-[18px]" />
          </Button>
        </header>
        <Outlet />
      </main>

      <Panels open={panel} onClose={() => setPanel(null)} />
    </div>
  )
}
