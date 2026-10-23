import { ArrowRight, Brain, CloudSun, FileSearch, Lock, Quote, Radio, Sparkles } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { Link } from "react-router"

import { BrandBackground } from "@/components/BrandBackground"
import { DemoReplay } from "@/components/DemoReplay"
import { Logo } from "@/components/Logo"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const REPO_URL = "https://github.com/vid6848/ContextAI"

// lucide no longer ships brand marks, so the GitHub logo is inlined
function GitHubMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" className={className} aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  )
}

/* ------------------------------------------------------------------ hero */

/** A floating card that bobs on its own and drifts with the pointer (depth = how far it moves). */
function Floating({
  depth,
  delay,
  tilt,
  className,
  children,
}: {
  depth: number
  delay: number
  tilt: number
  className: string
  children: React.ReactNode
}) {
  return (
    <div
      className={cn("pointer-events-none absolute hidden min-[1400px]:block", className)}
      style={{
        transform: `translate3d(calc(var(--mx, 0) * ${depth}px), calc(var(--my, 0) * ${depth}px), 0)`,
        transition: "transform 0.6s cubic-bezier(0.2, 0.8, 0.2, 1)",
      }}
    >
      <div className="animate-rise" style={{ animationDelay: `${0.6 + delay}s` }}>
        <div
          className="animate-float rounded-2xl border bg-card/85 p-4 shadow-[0_24px_60px_-28px_rgb(30_20_90/0.45)] backdrop-blur-xl"
          style={{ animationDelay: `${delay * 2}s`, ["--tilt" as string]: `${tilt}deg` }}
        >
          {children}
        </div>
      </div>
    </div>
  )
}

function Hero() {
  const ref = useRef<HTMLElement>(null)

  // Pointer position as -1..1 CSS variables; the floating cards translate by it for a parallax feel
  const onMove = (e: React.PointerEvent) => {
    const el = ref.current
    if (!el || e.pointerType !== "mouse") return
    const r = el.getBoundingClientRect()
    el.style.setProperty("--mx", (((e.clientX - r.left) / r.width) * 2 - 1).toFixed(3))
    el.style.setProperty("--my", (((e.clientY - r.top) / r.height) * 2 - 1).toFixed(3))
  }

  return (
    <section ref={ref} onPointerMove={onMove} className="relative isolate flex min-h-dvh flex-col">
      <BrandBackground />

      <header className="mx-auto flex w-full max-w-[96rem] items-center justify-between px-6 py-5 sm:px-10">
        <Link to="/" className="flex items-center gap-2.5">
          <Logo className="size-7" />
          <span className="font-display text-[1.25rem] font-semibold tracking-[-0.02em]">ContextAI</span>
        </Link>
        <nav className="flex items-center gap-1 sm:gap-2">
          <a href="#demo" className="hidden rounded-full px-4 py-2 text-[0.95rem] text-muted-foreground hover:text-foreground sm:block">
            How it works
          </a>
          <a href="#features" className="hidden rounded-full px-4 py-2 text-[0.95rem] text-muted-foreground hover:text-foreground sm:block">
            Features
          </a>
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer noopener"
            aria-label="Source code on GitHub"
            className="rounded-full p-2.5 text-muted-foreground hover:text-foreground"
          >
            <GitHubMark className="size-5" />
          </a>
          <Button asChild className="ml-1 h-10 rounded-full px-5 text-[0.95rem]">
            <Link to="/chat">Open app</Link>
          </Button>
        </nav>
      </header>

      <div className="relative mx-auto flex w-full max-w-[96rem] flex-1 flex-col items-center justify-center px-6 pb-24 text-center sm:px-10">
        <p
          className="animate-rise inline-flex items-center gap-2 rounded-full border bg-card/70 px-4 py-1.5 text-[0.9rem] text-muted-foreground backdrop-blur"
          style={{ animationDelay: "0.05s" }}
        >
          <span className="relative flex size-2">
            <span className="absolute inset-0 animate-ping rounded-full bg-step-docs/70" />
            <span className="relative size-2 rounded-full bg-step-docs" />
          </span>
          Open source, with a live view of every step
        </p>

        <h1
          className="animate-rise mt-7 max-w-[13ch] font-display text-[clamp(3.25rem,7.2vw,7rem)] leading-[0.95] font-semibold tracking-[-0.045em]"
          style={{ animationDelay: "0.15s" }}
        >
          An assistant that <span className="text-gradient">shows its work.</span>
        </h1>

        <p
          className="animate-rise mt-7 max-w-[40ch] text-[clamp(1.1rem,1.6vw,1.4rem)] leading-relaxed text-muted-foreground"
          style={{ animationDelay: "0.3s" }}
        >
          ContextAI remembers what you tell it, checks live data, and reads your PDFs. Every answer comes with the
          steps it took and the sources it used.
        </p>

        <div className="animate-rise mt-10 flex flex-wrap justify-center gap-3" style={{ animationDelay: "0.45s" }}>
          <Link
            to="/chat"
            className="group bg-brand-gradient inline-flex h-14 items-center gap-2 rounded-full px-8 text-[1.05rem] font-semibold text-white shadow-[0_18px_40px_-14px_rgb(91_71_245/0.7)] transition-transform hover:-translate-y-0.5"
          >
            Start chatting
            <ArrowRight className="size-5 transition-transform group-hover:translate-x-0.5" />
          </Link>
          <a
            href="#demo"
            className="inline-flex h-14 items-center rounded-full border bg-card/70 px-8 text-[1.05rem] font-medium backdrop-blur transition-colors hover:bg-card"
          >
            See it work
          </a>
        </div>
        <p className="animate-rise mt-5 text-[0.9rem] text-muted-foreground" style={{ animationDelay: "0.55s" }}>
          No sign-up. Your chats stay private to this browser.
        </p>

        {/* Floating previews of what an answer can contain */}
        <Floating depth={-18} delay={0} tilt={-3} className="top-[1%] left-[2%] w-[14.5rem]">
          <div className="flex items-center gap-3">
            <CloudSun className="size-10 text-step-tool" strokeWidth={1.5} />
            <div className="text-left">
              <p className="text-[0.8rem] text-muted-foreground">Tokyo, JP</p>
              <p className="font-display text-[1.6rem] leading-none font-semibold">
                18°C <span className="text-[0.85rem] font-normal text-muted-foreground">Broken clouds</span>
              </p>
            </div>
          </div>
        </Floating>

        <Floating depth={-26} delay={0.3} tilt={2} className="bottom-[13%] left-[4%] w-[16rem]">
          <div className="flex items-start gap-3 text-left">
            <span className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-lg bg-step-memory/15 text-step-memory">
              <Brain className="size-4" />
            </span>
            <div>
              <p className="text-[0.8rem] font-medium text-step-memory">Remembered</p>
              <p className="text-[0.92rem] leading-snug">You prefer answers with Python examples</p>
            </div>
          </div>
        </Floating>

        <Floating depth={22} delay={0.15} tilt={3} className="top-[3%] right-[2%] w-[13rem]">
          <div className="text-left">
            <p className="text-[0.8rem] text-muted-foreground">Bitcoin</p>
            <p className="font-display text-[1.6rem] leading-tight font-semibold tabular-nums">$81,644</p>
            <p className="text-[0.85rem] font-medium text-step-docs">▲ 0.84% today</p>
          </div>
        </Floating>

        <Floating depth={30} delay={0.45} tilt={-2} className="right-[3%] bottom-[11%] w-[17rem]">
          <div className="text-left">
            <p className="flex items-center gap-2 text-[0.8rem] text-muted-foreground">
              <span className="flex h-5 min-w-5 items-center justify-center rounded-md bg-step-docs/15 px-1 text-[0.7rem] font-semibold text-step-docs">
                1
              </span>
              northwind_q3.pdf, page 2
            </p>
            <p className="mt-2 flex gap-2 text-[0.92rem] leading-snug">
              <Quote className="size-4 shrink-0 text-muted-foreground" />
              Risks: supplier delays and rising cloud costs (up 12%).
            </p>
          </div>
        </Floating>
      </div>

      <a
        href="#demo"
        aria-label="Scroll to the demo"
        className="absolute bottom-7 left-1/2 hidden -translate-x-1/2 flex-col items-center gap-2 text-[0.8rem] text-muted-foreground sm:flex"
      >
        <span className="flex h-9 w-6 justify-center rounded-full border-2 border-muted-foreground/40 pt-1.5">
          <span className="h-2 w-1 animate-bounce rounded-full bg-muted-foreground/60" />
        </span>
      </a>
    </section>
  )
}

/* ------------------------------------------------------------------ demo */

function useInView<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [inView, setInView] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setInView(true), { threshold: 0.35 })
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return { ref, inView }
}

const TRACE_LEGEND = [
  { dot: "bg-step-memory", label: "Memory", text: "what it recalled about you" },
  { dot: "bg-step-route", label: "Routing", text: "how it decided what to do" },
  { dot: "bg-step-tool", label: "Tools", text: "live data it fetched, with the raw result" },
  { dot: "bg-step-docs", label: "Documents", text: "the passages it read, page by page" },
]

function Demo() {
  const { ref, inView } = useInView<HTMLDivElement>()
  const [run, setRun] = useState(0)
  return (
    <section id="demo" className="scroll-mt-8 border-t bg-card/40">
      <div className="mx-auto grid max-w-[96rem] items-center gap-14 px-6 py-24 sm:px-10 lg:grid-cols-[0.9fr_1.1fr] lg:py-32">
        <div>
          <h2 className="font-display text-[clamp(2.25rem,4vw,3.5rem)] leading-[1.05] font-semibold">
            Watch the answer happen.
          </h2>
          <p className="mt-5 max-w-[44ch] text-[1.15rem] leading-relaxed text-muted-foreground">
            Most chatbots hand you a finished paragraph. ContextAI shows the work as it happens, colour-coded so you
            can tell at a glance where an answer came from.
          </p>
          <dl className="mt-8 space-y-3.5">
            {TRACE_LEGEND.map((l) => (
              <div key={l.label} className="flex items-baseline gap-3 text-[1.05rem]">
                <span className={cn("size-2.5 shrink-0 translate-y-[-2px] rounded-full", l.dot)} aria-hidden />
                <dt className="font-semibold">{l.label}</dt>
                <dd className="text-muted-foreground">{l.text}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div ref={ref} className="min-h-[24rem]">
          {inView && <DemoReplay key={run} onReplay={() => setRun((r) => r + 1)} />}
        </div>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ features */

const FEATURES = [
  { icon: Brain, color: "text-step-memory bg-step-memory/12", title: "Remembers what matters", body: "Tell it once that you live in Pune or prefer short answers. It brings that up in later chats, and you can wipe it any time." },
  { icon: Radio, color: "text-step-tool bg-step-tool/12", title: "Checks live data", body: "Weather, crypto prices, web search and a calculator, picked automatically and shown as cards, not walls of text." },
  { icon: FileSearch, color: "text-step-docs bg-step-docs/12", title: "Reads your PDFs", body: "Drop in a report or a lease. Answers cite the exact passage and page, one click away." },
  { icon: Sparkles, color: "text-step-route bg-step-route/12", title: "Streams as it thinks", body: "Words appear as they're written. Stop it, regenerate it, or edit your question and try again." },
  { icon: Quote, color: "text-step-docs bg-step-docs/12", title: "Cites its sources", body: "Every claim from a document or the web carries a numbered citation you can open and check." },
  { icon: Lock, color: "text-step-memory bg-step-memory/12", title: "Private by default", body: "No account needed. Your chats, memories and files are visible only to you." },
]

function Features() {
  return (
    <section id="features" className="scroll-mt-8">
      <div className="mx-auto max-w-[96rem] px-6 py-24 sm:px-10 lg:py-32">
        <h2 className="max-w-[18ch] font-display text-[clamp(2.25rem,4vw,3.5rem)] leading-[1.05] font-semibold">
          Everything a good assistant should do, out in the open.
        </h2>
        <div className="mt-14 grid gap-x-10 gap-y-12 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title}>
              <span className={cn("flex size-12 items-center justify-center rounded-2xl", f.color)}>
                <f.icon className="size-6" />
              </span>
              <h3 className="mt-5 font-display text-[1.35rem] font-semibold">{f.title}</h3>
              <p className="mt-2 max-w-[40ch] text-[1.05rem] leading-relaxed text-muted-foreground">{f.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

const STACK = ["FastAPI", "LangGraph", "Gemini via LiteLLM", "ChromaDB", "SQLite", "Server-Sent Events", "React 19", "TypeScript", "Tailwind CSS", "shadcn/ui", "Docker", "GitHub Actions"]

function Closing() {
  return (
    <section className="px-6 pb-16 sm:px-10">
      <div className="relative isolate mx-auto max-w-[96rem] overflow-hidden rounded-[2rem] bg-brand-gradient px-8 py-16 text-white sm:px-16 sm:py-20">
        <div className="absolute -top-24 -right-24 -z-10 size-96 rounded-full bg-white/15 blur-3xl" aria-hidden />
        <h2 className="max-w-[16ch] font-display text-[clamp(2.25rem,4.5vw,4rem)] leading-[1.02] font-semibold">
          Ask it something. Watch how it answers.
        </h2>
        <Link
          to="/chat"
          className="group mt-9 inline-flex h-14 items-center gap-2 rounded-full bg-white px-8 text-[1.05rem] font-semibold text-[#2a1f8f] transition-transform hover:-translate-y-0.5"
        >
          Start chatting
          <ArrowRight className="size-5 transition-transform group-hover:translate-x-0.5" />
        </Link>
        <p className="mt-12 text-[0.95rem] text-white/75">Built with</p>
        <ul className="mt-3 flex flex-wrap gap-2">
          {STACK.map((s) => (
            <li key={s} className="rounded-full bg-white/15 px-3.5 py-1.5 text-[0.9rem] backdrop-blur">
              {s}
            </li>
          ))}
        </ul>
      </div>
      <footer className="mx-auto mt-10 flex max-w-[96rem] flex-wrap items-center justify-between gap-4 text-[0.95rem] text-muted-foreground">
        <span className="flex items-center gap-2">
          <Logo className="size-5" /> ContextAI
        </span>
        <a href={REPO_URL} target="_blank" rel="noreferrer noopener" className="flex items-center gap-2 hover:text-foreground">
          <GitHubMark className="size-4" /> Source on GitHub
        </a>
      </footer>
    </section>
  )
}

function LandingPage() {
  return (
    <div className="h-dvh overflow-y-auto scroll-smooth">
      <Hero />
      <Demo />
      <Features />
      <Closing />
    </div>
  )
}

export default LandingPage
