import type { Session, SupabaseClient } from "@supabase/supabase-js"
import { create } from "zustand"

/** Sign-in with Supabase Auth. The server tells us the (public) project URL and key via /api/v1/config. */

interface AuthConfig {
  supabase_url: string
  publishable_key: string
  required: boolean
}

interface AuthState {
  /** false until the config (and any existing session) has loaded */
  ready: boolean
  /** sign-in is configured on this server */
  enabled: boolean
  required: boolean
  session: Session | null
  signInWithGoogle: () => Promise<void>
  sendMagicLink: (email: string) => Promise<void>
  signOut: () => Promise<void>
}

let client: SupabaseClient | null = null
const GUEST_KEY = "contextai_user_id"
const claimedKey = (guest: string, account: string) => `contextai_claimed_${guest}_${account}`

/** Current access token, for the Authorization header (undefined for guests). */
export function accessToken(): string | undefined {
  return useAuth.getState().session?.access_token
}

/** Move this browser's guest data into the account, once per guest/account pair. */
async function claimGuestData(session: Session): Promise<boolean> {
  const guest = localStorage.getItem(GUEST_KEY)
  if (!guest) return false
  const key = claimedKey(guest, session.user.id)
  if (localStorage.getItem(key)) return false
  const resp = await fetch("/api/v1/auth/claim", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.access_token}` },
    body: JSON.stringify({ guest_id: guest }),
  })
  if (!resp.ok) return false
  localStorage.setItem(key, "1")
  const { moved } = (await resp.json()) as { moved: Record<string, number> }
  return Object.values(moved).some((n) => n > 0)
}

const redirectTo = () => `${window.location.origin}/chat`

export const useAuth = create<AuthState>((set) => ({
  ready: false,
  enabled: false,
  required: false,
  session: null,
  async signInWithGoogle() {
    if (!client) return
    const { error } = await client.auth.signInWithOAuth({ provider: "google", options: { redirectTo: redirectTo() } })
    if (error) throw error
  },
  async sendMagicLink(email: string) {
    if (!client) return
    const { error } = await client.auth.signInWithOtp({ email, options: { emailRedirectTo: redirectTo() } })
    if (error) throw error
  },
  async signOut() {
    await client?.auth.signOut()
    set({ session: null })
  },
}))

type Listener = (event: "signed-in" | "signed-out", guestDataMoved: boolean) => void
const listeners = new Set<Listener>()

/** Called when the identity changes, so the chat list can reload for the new user. */
export function onIdentityChange(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

let started = false

export async function initAuth(): Promise<void> {
  if (started) return
  started = true
  let config: AuthConfig | null = null
  try {
    config = ((await (await fetch("/api/v1/config")).json()) as { auth: AuthConfig | null }).auth
  } catch {
    config = null
  }
  if (!config) {
    useAuth.setState({ ready: true, enabled: false })
    return
  }

  const { createClient } = await import("@supabase/supabase-js")
  client = createClient(config.supabase_url, config.publishable_key, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true, flowType: "pkce" },
  })
  const { data } = await client.auth.getSession()
  useAuth.setState({ ready: true, enabled: true, required: config.required, session: data.session })
  if (data.session) await claimGuestData(data.session).catch(() => false)

  client.auth.onAuthStateChange((event, session) => {
    const previous = useAuth.getState().session
    useAuth.setState({ session })
    if (event === "SIGNED_IN" && session && previous?.user.id !== session.user.id) {
      void claimGuestData(session)
        .catch(() => false)
        .then((moved) => listeners.forEach((l) => l("signed-in", moved)))
    } else if (event === "SIGNED_OUT") {
      listeners.forEach((l) => l("signed-out", false))
    }
  })
}
