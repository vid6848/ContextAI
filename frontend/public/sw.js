/* ContextAI service worker: shows reminder notifications pushed by the server, even with no tab open. */
self.addEventListener("install", () => self.skipWaiting())
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()))

self.addEventListener("push", (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch {
    data = { body: event.data ? event.data.text() : "" }
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "ContextAI", {
      body: data.body || "",
      tag: data.tag,
      icon: "/favicon.svg",
      badge: "/favicon.svg",
      data: { url: data.url || "/chat" },
    }),
  )
})

self.addEventListener("notificationclick", (event) => {
  event.notification.close()
  const url = (event.notification.data && event.notification.data.url) || "/chat"
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      const open = windows.find((w) => new URL(w.url).origin === self.location.origin)
      if (open) {
        open.focus()
        return open.navigate(url)
      }
      return self.clients.openWindow(url)
    }),
  )
})
