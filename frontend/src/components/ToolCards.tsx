import { BellRing, Cloud, CloudDrizzle, CloudFog, CloudLightning, CloudRain, CloudSnow, Droplets, Sun, Wind } from "lucide-react"

import type { CryptoOutput, ForecastOutput, ReminderOutput, WeatherOutput } from "@/lib/types"
import { formatWhen } from "@/lib/when"
import { cn } from "@/lib/utils"

function WeatherIcon({ condition = "", className }: { condition?: string; className?: string }) {
  const c = condition.toLowerCase()
  const props = { className, strokeWidth: 1.5, "aria-hidden": true }
  if (c.includes("thunder")) return <CloudLightning {...props} />
  if (c.includes("drizzle")) return <CloudDrizzle {...props} />
  if (c.includes("rain")) return <CloudRain {...props} />
  if (c.includes("snow")) return <CloudSnow {...props} />
  if (["mist", "fog", "haze", "smoke"].some((k) => c.includes(k))) return <CloudFog {...props} />
  if (c.includes("cloud")) return <Cloud {...props} />
  return <Sun {...props} />
}

const round = (n?: number | null) => (typeof n === "number" ? Math.round(n) : "–")

export function ForecastCard({ data }: { data: ForecastOutput }) {
  const unit = data.units === "fahrenheit" ? "°F" : "°C"
  const hours = data.hours ?? []
  return (
    <figure
      className="mb-4 rounded-2xl border bg-card/85 px-4 py-4 shadow-[0_18px_40px_-26px_rgb(30_20_90/0.4)] backdrop-blur-xl sm:px-5"
      aria-label={`Forecast for ${data.location}`}
    >
      <figcaption className="mb-3 truncate text-sm text-muted-foreground">Forecast for {data.location}</figcaption>
      <ul className="grid grid-cols-[repeat(auto-fit,minmax(5.25rem,1fr))] gap-2">
        {data.days.map((day) => (
          <li key={day.date} className="min-w-0 rounded-xl bg-background/60 px-2 py-2.5 text-center">
            <p className="truncate text-[0.8125rem] font-medium">{day.date === data.today ? "Today" : day.weekday.slice(0, 3)}</p>
            <WeatherIcon condition={day.condition} className="mx-auto my-1.5 size-7 text-step-tool" />
            <p className="text-sm tabular-nums">
              {round(day.high)}
              {unit} <span className="text-muted-foreground">{round(day.low)}°</span>
            </p>
            <p className="mt-0.5 flex items-center justify-center gap-1 text-xs tabular-nums text-muted-foreground">
              <Droplets className="size-3" aria-label="Chance of rain" /> {day.rain_chance_percent}%
            </p>
          </li>
        ))}
      </ul>
      {hours.length > 0 && (
        <ul className="mt-3 flex gap-4 overflow-x-auto pb-1 text-center text-xs tabular-nums [overscroll-behavior-x:contain]">
          {hours.map((h) => (
            <li key={h.time} className="shrink-0">
              <p className="text-muted-foreground">{h.time}</p>
              <p className="text-sm">
                {round(h.temperature)}
                {unit}
              </p>
              <p className="text-muted-foreground">{h.rain_chance_percent}%</p>
            </li>
          ))}
        </ul>
      )}
    </figure>
  )
}

export function WeatherCard({ data }: { data: WeatherOutput }) {
  const unit = data.units === "fahrenheit" ? "°F" : "°C"
  const wind = data.units === "fahrenheit" ? "mph" : "m/s"
  return (
    <figure className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-3 rounded-2xl border bg-card/85 px-5 py-4 shadow-[0_18px_40px_-26px_rgb(30_20_90/0.4)] backdrop-blur-xl" aria-label={`Weather in ${data.location}`}>
      <WeatherIcon condition={data.condition} className="size-11 shrink-0 text-step-tool" />
      <div className="min-w-0 flex-1 basis-40">
        <figcaption className="truncate text-sm text-muted-foreground">{data.location}</figcaption>
        <p className="flex items-baseline gap-2">
          <span className="text-[2.25rem] leading-tight font-medium tabular-nums tracking-tight">
            {round(data.temperature)}
            {unit}
          </span>
          <span className="truncate text-[0.9375rem] capitalize text-foreground/80">{data.description ?? data.condition}</span>
        </p>
      </div>
      <dl className="flex w-full flex-wrap gap-x-5 gap-y-1 text-sm text-muted-foreground sm:w-auto sm:shrink-0 sm:flex-col">
        {data.feels_like != null && (
          <div className="flex justify-between gap-4">
            <dt>Feels like</dt>
            <dd className="tabular-nums text-foreground/85">
              {round(data.feels_like)}
              {unit}
            </dd>
          </div>
        )}
        {data.humidity != null && (
          <div className="flex justify-between gap-4">
            <dt className="flex items-center gap-1">
              <Droplets className="size-3.5" aria-hidden /> Humidity
            </dt>
            <dd className="tabular-nums text-foreground/85">{data.humidity}%</dd>
          </div>
        )}
        {data.wind_speed != null && (
          <div className="flex justify-between gap-4">
            <dt className="flex items-center gap-1">
              <Wind className="size-3.5" aria-hidden /> Wind
            </dt>
            <dd className="tabular-nums text-foreground/85">
              {Math.round(data.wind_speed)} {wind}
            </dd>
          </div>
        )}
      </dl>
    </figure>
  )
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 })
const compactUsd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 2 })

export function CryptoCard({ data }: { data: CryptoOutput }) {
  const change = data.change_24h_percent
  const up = (change ?? 0) >= 0
  const name = data.coin.replace(/-/g, " ")
  return (
    <figure className="mb-4 flex flex-wrap items-end gap-x-6 gap-y-2 rounded-2xl border bg-card/85 px-5 py-4 shadow-[0_18px_40px_-26px_rgb(30_20_90/0.4)] backdrop-blur-xl" aria-label={`${name} price`}>
      <div>
        <figcaption className="text-sm capitalize text-muted-foreground">{name}</figcaption>
        <p className="text-[1.875rem] leading-tight font-medium tabular-nums tracking-tight">{usd.format(data.price_usd)}</p>
      </div>
      {change != null && (
        <p className={cn("pb-1 text-[0.9375rem] font-medium tabular-nums", up ? "text-step-docs" : "text-step-error")}>
          {up ? "▲" : "▼"} {Math.abs(change).toFixed(2)}% <span className="font-normal text-muted-foreground">24h</span>
        </p>
      )}
      {data.market_cap_usd != null && (
        <p className="ml-auto pb-1 text-sm text-muted-foreground">
          Market cap <span className="tabular-nums text-foreground/85">{compactUsd.format(data.market_cap_usd)}</span>
        </p>
      )}
    </figure>
  )
}

export function ReminderCard({ data }: { data: ReminderOutput }) {
  return (
    <figure
      className="mb-4 flex items-center gap-4 rounded-2xl border bg-card/85 px-5 py-4 shadow-[0_18px_40px_-26px_rgb(30_20_90/0.4)] backdrop-blur-xl"
      aria-label={`Reminder: ${data.text}`}
    >
      <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-brand/12 text-brand">
        <BellRing className="size-5" />
      </span>
      <div className="min-w-0">
        <figcaption className="text-sm text-muted-foreground">Reminder set</figcaption>
        <p className="truncate font-display text-[1.25rem] font-semibold">{data.text}</p>
        <p className="text-[0.95rem] text-foreground/80">{formatWhen(data.due_at)}</p>
      </div>
    </figure>
  )
}

export function ToolCard({ tool, output }: { tool?: string | null; output?: Record<string, unknown> | null }) {
  if (!output) return null
  if (tool === "weather" && "days" in output) return <ForecastCard data={output as unknown as ForecastOutput} />
  if (tool === "weather") return <WeatherCard data={output as unknown as WeatherOutput} />
  if (tool === "crypto") return <CryptoCard data={output as unknown as CryptoOutput} />
  if (tool === "reminder") return <ReminderCard data={output as unknown as ReminderOutput} />
  return null
}
