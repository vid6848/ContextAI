import { api } from "./api"

export type PushState = "unsupported" | "denied" | "off" | "on"

const supported = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window

export function registerServiceWorker() {
  if (supported()) void navigator.serviceWorker.register("/sw.js").catch(() => undefined)
}

export async function pushState(): Promise<PushState> {
  if (!supported()) return "unsupported"
  if (Notification.permission === "denied") return "denied"
  const reg = await navigator.serviceWorker.getRegistration()
  const sub = await reg?.pushManager.getSubscription()
  return sub && Notification.permission === "granted" ? "on" : "off"
}

function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const padded = (base64url + "=".repeat((4 - (base64url.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/")
  const raw = atob(padded)
  const out = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i)
  return out
}

/** Ask permission, subscribe this browser to push, and register the subscription with the server. */
export async function enablePush(): Promise<PushState> {
  if (!supported()) return "unsupported"
  const permission = await Notification.requestPermission()
  if (permission !== "granted") return permission === "denied" ? "denied" : "off"
  const reg = await navigator.serviceWorker.register("/sw.js")
  await navigator.serviceWorker.ready
  const publicKey = await api.pushPublicKey()
  const sub =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(publicKey) }))
  await api.pushSubscribe(sub.toJSON())
  return "on"
}

