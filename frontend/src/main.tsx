import { ThemeProvider } from "next-themes"
import { lazy, StrictMode, Suspense } from "react"
import { createRoot } from "react-dom/client"
import { createBrowserRouter, Navigate } from "react-router"
import { RouterProvider } from "react-router/dom"

import { AppLayout } from "@/App"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { initAuth } from "@/lib/auth"
import { registerServiceWorker } from "@/lib/push"
import { ChatPage } from "@/pages/ChatPage"
import { MemoryPage } from "@/pages/MemoryPage"
import { NotFoundPage } from "@/pages/NotFoundPage"

const LandingPage = lazy(() => import("@/pages/LandingPage"))

import "./index.css"

const router = createBrowserRouter([
  {
    element: <AppLayout />,
    errorElement: <NotFoundPage />,
    children: [
      { path: "/chat", element: <ChatPage /> },
      { path: "/c/:id", element: <ChatPage /> },
      { path: "/memory", element: <MemoryPage /> },
    ],
  },
  {
    path: "/",
    element: (
      <Suspense fallback={null}>
        <LandingPage />
      </Suspense>
    ),
  },
  { path: "/welcome", element: <Navigate to="/" replace /> },
  { path: "*", element: <NotFoundPage /> },
])

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {/* The SPA renders on the client, where next-themes' inline script never runs anyway; marking it as a data
        block stops React warning about it on every load. */}
    <ThemeProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
      scriptProps={{ type: "application/json" }}
    >
      <TooltipProvider delayDuration={400}>
        <RouterProvider router={router} />
        {/* Top: at the bottom it would sit on the message box on phones */}
        <Toaster position="top-center" mobileOffset={{ top: "max(16px, env(safe-area-inset-top))" }} />
      </TooltipProvider>
    </ThemeProvider>
  </StrictMode>,
)

registerServiceWorker()
void initAuth()
