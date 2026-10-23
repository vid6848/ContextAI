import { Cloud, CloudDrizzle, CloudFog, CloudLightning, CloudRain, CloudSnow, Droplets, Sun, Wind } from "lucide-react"

import type { CryptoOutput, WeatherOutput } from "@/lib/types"
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

export function WeatherCard({ data }: { data: WeatherOutput }) {
  const unit = data.units === "fahrenheit" ? "°F" : "°C"
  return (
    <figure className="mb-4 flex items-center gap-5 rounded-2xl border bg-card px-5 py-4" aria-label={`Weather in ${data.location}`}>
      <WeatherIcon condition={data.condition} className="size-11 shrink-0 text-step-tool" />
      <div className="min-w-0 flex-1">
        <figcaption className="truncate text-sm text-muted-foreground">{data.location}</figcaption>
        <p className="flex items-baseline gap-2">
          <span className="text-[2.25rem] leading-tight font-medium tabular-nums tracking-tight">
            {round(data.temperature)}
            {unit}
          </span>
          <span className="truncate text-[0.9375rem] capitalize text-foreground/80">{data.description ?? data.condition}</span>
        </p>
      </div>
      <dl className="hidden shrink-0 space-y-1 text-sm text-muted-foreground sm:block">
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
            <dd className="tabular-nums text-foreground/85">{data.wind_speed} m/s</dd>
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
    <figure className="mb-4 flex flex-wrap items-end gap-x-6 gap-y-2 rounded-2xl border bg-card px-5 py-4" aria-label={`${name} price`}>
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

export function ToolCard({ tool, output }: { tool?: string | null; output?: Record<string, unknown> | null }) {
  if (!output) return null
  if (tool === "weather") return <WeatherCard data={output as unknown as WeatherOutput} />
  if (tool === "crypto") return <CryptoCard data={output as unknown as CryptoOutput} />
  return null
}
