import { ThemeProvider } from "next-themes"
import { lazy, StrictMode, Suspense } from "react"
import { createRoot } from "react-dom/client"
import { createBrowserRouter } from "react-router"
import { RouterProvider } from "react-router/dom"

import { AppLayout } from "@/App"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { ChatPage } from "@/pages/ChatPage"
import { NotFoundPage } from "@/pages/NotFoundPage"

const WelcomePage = lazy(() => import("@/pages/WelcomePage"))

import "./index.css"

const router = createBrowserRouter([
  {
    element: <AppLayout />,
    errorElement: <NotFoundPage />,
    children: [
      { path: "/", element: <ChatPage /> },
      { path: "/c/:id", element: <ChatPage /> },
    ],
  },
  {
    path: "/welcome",
    element: (
      <Suspense fallback={null}>
        <WelcomePage />
      </Suspense>
    ),
  },
  { path: "*", element: <NotFoundPage /> },
])

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <TooltipProvider delayDuration={400}>
        <RouterProvider router={router} />
        <Toaster position="bottom-center" />
      </TooltipProvider>
    </ThemeProvider>
  </StrictMode>,
)
