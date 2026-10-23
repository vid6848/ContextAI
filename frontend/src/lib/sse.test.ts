import { describe, expect, it } from "vitest"

import { parseSSE } from "./sse"

function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(enc.encode(c))
      controller.close()
    },
  })
}

async function collect(body: ReadableStream<Uint8Array>) {
  const out = []
  for await (const e of parseSSE(body)) out.push(e)
  return out
}

describe("parseSSE", () => {
  it("parses named events with JSON data", async () => {
    const events = await collect(streamOf('event: token\ndata: {"text":"Hi"}\n\nevent: done\ndata: {}\n\n'))
    expect(events).toEqual([
      { event: "token", data: { text: "Hi" } },
      { event: "done", data: {} },
    ])
  })

  it("reassembles events split across network chunks", async () => {
    const events = await collect(streamOf("event: tok", 'en\ndata: {"te', 'xt":"a"}\n', "\n"))
    expect(events).toEqual([{ event: "token", data: { text: "a" } }])
  })

  it("handles multi-byte characters split between chunks", async () => {
    const bytes = new TextEncoder().encode('event: token\ndata: {"text":"héllo 👋"}\n\n')
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(bytes.slice(0, 30))
        c.enqueue(bytes.slice(30))
        c.close()
      },
    })
    expect((await collect(body))[0].data).toEqual({ text: "héllo 👋" })
  })

  it("defaults the event name to message and flushes a trailing block", async () => {
    expect(await collect(streamOf('data: {"a":1}'))).toEqual([{ event: "message", data: { a: 1 } }])
  })
})
