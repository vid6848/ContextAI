import {
  Bell,
  Brain,
  FileText,
  Info,
  Keyboard,
  LogIn,
  LogOut,
  Monitor,
  Moon,
  MoreHorizontal,
  PanelLeftClose,
  Pencil,
  Search,
  SquarePen,
  Sun,
  Trash2,
  UserRound,
} from "lucide-react"
import { useTheme } from "next-themes"
import { useMemo, useState } from "react"
import { NavLink, useNavigate } from "react-router"
import { toast } from "sonner"

import { Logo } from "@/components/Logo"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { isTouchDevice } from "@/hooks/useMediaQuery"
import { useAuth } from "@/lib/auth"
import { groupConversations } from "@/lib/dates"
import { MOD } from "@/lib/platform"
import type { Conversation } from "@/lib/types"
import { cn } from "@/lib/utils"
import { useChat } from "@/store/chat"

export type Panel = "documents" | "reminders" | "memory" | "shortcuts" | "signin"

interface AppSidebarProps {
  onNavigate?: () => void
  onCollapse?: () => void
  onOpenPanel: (panel: Panel) => void
  searchRef?: React.Ref<HTMLInputElement>
}

export function AppSidebar({ onNavigate, onCollapse, onOpenPanel, searchRef }: AppSidebarProps) {
  const conversations = useChat((s) => s.conversations)
  const loaded = useChat((s) => s.conversationsLoaded)
  const [query, setQuery] = useState("")
  const navigate = useNavigate()

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase()
    return groupConversations(q ? conversations.filter((c) => c.title.toLowerCase().includes(q)) : conversations)
  }, [conversations, query])

  return (
    <div className="flex h-full flex-col bg-sidebar/75 text-sidebar-foreground backdrop-blur-xl">
      <div className="flex items-center justify-between px-3 pt-3 pb-2">
        <NavLink to="/" onClick={onNavigate} title="ContextAI home" className="flex items-center gap-2 rounded-md px-1.5 py-1">
          <Logo className="size-[1.375rem]" />
          <span className="font-display text-[1.1rem] font-semibold tracking-[-0.02em]">ContextAI</span>
        </NavLink>
        {onCollapse && (
          <Button variant="ghost" size="icon" onClick={onCollapse} aria-label="Close sidebar" className="text-muted-foreground">
            <PanelLeftClose className="size-[1.125rem]" />
          </Button>
        )}
      </div>

      <div className="space-y-1 px-2">
        <Button
          variant="ghost"
          className="h-9 w-full justify-start gap-2.5 px-2.5 text-[0.9rem] font-normal touch:h-11"
          onClick={() => {
            navigate("/chat")
            onNavigate?.()
          }}
        >
          <SquarePen className="size-4" />
          New chat
          <kbd className="ml-auto font-sans text-xs text-muted-foreground touch:hidden">{MOD}⇧O</kbd>
        </Button>
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <input
            ref={searchRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={isTouchDevice() ? "Search chats" : `Search chats  ${MOD}K`}
            aria-label="Search chats"
            className="h-9 w-full rounded-md bg-transparent pr-2 touch:h-11 pl-[34px] text-[0.9rem] outline-none placeholder:text-muted-foreground hover:bg-sidebar-accent focus:bg-sidebar-accent"
          />
        </div>
      </div>

      <nav className="mt-3 flex-1 overflow-y-auto px-2 pb-2" aria-label="Conversations">
        {loaded && !groups.length && (
          <p className="px-2.5 py-2 text-[0.8125rem] text-muted-foreground">
            {query ? "No chats match that search." : "Your chats will appear here."}
          </p>
        )}
        {groups.map((g) => (
          <section key={g.label} className="mb-4">
            <h2 className="px-2.5 pb-1 text-[0.75rem] font-medium text-muted-foreground">{g.label}</h2>
            <ul>
              {g.items.map((c) => (
                <ConversationRow key={c.id} conversation={c} onNavigate={onNavigate} />
              ))}
            </ul>
          </section>
        ))}
      </nav>

      <div className="border-t border-sidebar-border p-2">
        <AccountMenu onOpenPanel={onOpenPanel} />
      </div>
    </div>
  )
}

function ConversationRow({ conversation, onNavigate }: { conversation: Conversation; onNavigate?: () => void }) {
  const rename = useChat((s) => s.rename)
  const remove = useChat((s) => s.remove)
  const activeId = useChat((s) => s.activeId)
  const navigate = useNavigate()
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(conversation.title)

  const commit = async () => {
    setEditing(false)
    const next = title.trim()
    if (!next || next === conversation.title) return setTitle(conversation.title)
    try {
      await rename(conversation.id, next)
    } catch {
      setTitle(conversation.title)
      toast.error("Couldn't rename the chat.")
    }
  }

  if (editing) {
    return (
      <li>
        <input
          autoFocus
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit()
            if (e.key === "Escape") {
              setTitle(conversation.title)
              setEditing(false)
            }
          }}
          aria-label="Chat title"
          className="h-8 w-full rounded-md border border-ring/50 bg-background px-2.5 text-[0.9rem] outline-none touch:h-11"
        />
      </li>
    )
  }

  return (
    <li className="group/row relative">
      <NavLink
        to={`/c/${conversation.id}`}
        onClick={onNavigate}
        className={({ isActive }) =>
          cn(
            "block truncate rounded-md py-1.5 pr-8 pl-2.5 touch:py-2.5 touch:pr-11 text-[0.9rem] text-sidebar-foreground/85 hover:bg-sidebar-accent",
            isActive && "bg-sidebar-accent font-medium text-sidebar-foreground",
          )
        }
        title={conversation.title}
      >
        {conversation.title}
      </NavLink>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            aria-label={`Options for ${conversation.title}`}
            className="absolute top-1/2 right-1 flex size-7 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground opacity-0 group-hover/row:opacity-100 hover:text-foreground focus-visible:opacity-100 aria-expanded:opacity-100 max-md:opacity-100 touch:size-9 touch:opacity-100"
          >
            <MoreHorizontal className="size-4" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-40">
          <DropdownMenuItem onSelect={() => setEditing(true)}>
            <Pencil /> Rename
          </DropdownMenuItem>
          <DropdownMenuItem
            variant="destructive"
            onSelect={async () => {
              try {
                await remove(conversation.id)
                if (activeId === conversation.id) navigate("/chat")
                toast("Chat deleted")
              } catch {
                toast.error("Couldn't delete the chat.")
              }
            }}
          >
            <Trash2 /> Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </li>
  )
}

function AccountMenu({ onOpenPanel }: { onOpenPanel: (panel: Panel) => void }) {
  const { theme, setTheme } = useTheme()
  const navigate = useNavigate()
  const { enabled, session, signOut } = useAuth()
  const user = session?.user
  const meta = (user?.user_metadata ?? {}) as { full_name?: string; name?: string; avatar_url?: string }
  const name = meta.full_name || meta.name || user?.email || "Guest"
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="h-11 w-full justify-start gap-2.5 px-2 text-[0.9rem] font-normal">
          {meta.avatar_url ? (
            <img src={meta.avatar_url} alt="" referrerPolicy="no-referrer" className="size-7 rounded-full" />
          ) : (
            <span
              className={cn(
                "flex size-7 items-center justify-center rounded-full",
                user ? "bg-brand-gradient text-[0.8rem] font-semibold text-white" : "bg-sidebar-accent",
              )}
            >
              {user ? name.slice(0, 1).toUpperCase() : <UserRound className="size-4" />}
            </span>
          )}
          <span className="min-w-0 truncate text-left">
            {name}
            {!user && enabled && <span className="block text-xs text-muted-foreground">Sign in to sync</span>}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start" className="w-64">
        {user ? (
          <DropdownMenuLabel className="truncate text-xs font-normal text-muted-foreground">{user.email}</DropdownMenuLabel>
        ) : enabled ? (
          <DropdownMenuItem onSelect={() => onOpenPanel("signin")}>
            <LogIn /> Sign in
          </DropdownMenuItem>
        ) : null}
        {(user || enabled) && <DropdownMenuSeparator />}
        <DropdownMenuItem onSelect={() => navigate("/memory")}>
          <Brain /> Memory
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => onOpenPanel("documents")}>
          <FileText /> Your documents
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => onOpenPanel("reminders")}>
          <Bell /> Reminders
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => onOpenPanel("memory")}>
          <Trash2 /> Clear chats and memory
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => onOpenPanel("shortcuts")}>
          <Keyboard /> Keyboard shortcuts
          <DropdownMenuShortcut>{MOD}/</DropdownMenuShortcut>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => navigate("/")}>
          <Info /> About ContextAI
        </DropdownMenuItem>
        {user && (
          <DropdownMenuItem onSelect={() => void signOut()}>
            <LogOut /> Sign out
          </DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">Appearance</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={theme} onValueChange={setTheme}>
          <DropdownMenuRadioItem value="light">
            <Sun /> Light
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark">
            <Moon /> Dark
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="system">
            <Monitor /> System
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
