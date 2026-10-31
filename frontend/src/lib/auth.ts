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
  /** Google is switched on in the Supabase project, so its button can work */
  googleEnabled: boolean
  session: Session | null
  signInWithGoogle: () => Promise<void>
  signIn: (email: string, password: string) => Promise<void>
  /** Resolves false when the project still requires confirming the email before the first sign-in. */
  signUp: (email: string, password: string) => Promise<boolean>
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

const ACCOUNT_EXISTS = "That email already has an account. Sign in instead."

function friendlyError(message: string): string {
  if (/invalid login credentials/i.test(message)) return "Wrong email or password."
  if (/already registered/i.test(message)) return ACCOUNT_EXISTS
  if (/email not confirmed/i.test(message)) return "Confirm your email first, then sign in."
  return message
}

/** Which sign-in providers the Supabase project has switched on (public, read-only). */
async function isGoogleEnabled(config: AuthConfig): Promise<boolean> {
  try {
    const resp = await fetch(`${config.supabase_url}/auth/v1/settings`, { headers: { apikey: config.publishable_key } })
    const settings = (await resp.json()) as { external?: { google?: boolean } }
    return !!settings.external?.google
  } catch {
    return false
  }
}

const redirectTo = () => `${window.location.origin}/chat`

export const useAuth = create<AuthState>((set) => ({
  ready: false,
  enabled: false,
  required: false,
  googleEnabled: false,
  session: null,
  async signInWithGoogle() {
    if (!client) return
    const { error } = await client.auth.signInWithOAuth({ provider: "google", options: { redirectTo: redirectTo() } })
    if (error) throw error
  },
  async signIn(email, password) {
    if (!client) return
    const { error } = await client.auth.signInWithPassword({ email, password })
    if (error) throw new Error(friendlyError(error.message))
  },
  async signUp(email, password) {
    if (!client) return false
    const { data, error } = await client.auth.signUp({ email, password, options: { emailRedirectTo: redirectTo() } })
    if (error) throw new Error(friendlyError(error.message))
    // With email confirmation on, Supabase hides "already registered" behind a user with no identities
    if (data.user && data.user.identities?.length === 0) throw new Error(ACCOUNT_EXISTS)
    return !!data.session
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
  const [{ data }, googleEnabled] = await Promise.all([client.auth.getSession(), isGoogleEnabled(config)])
  useAuth.setState({ ready: true, enabled: true, required: config.required, googleEnabled, session: data.session })
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
