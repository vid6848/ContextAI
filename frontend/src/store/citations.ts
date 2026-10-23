import { create } from "zustand"

/** Which message's sources are open in the side panel, and which citation is highlighted. */
export const useCitations = create<{
  open: { messageKey: string; active: number } | null
  show: (messageKey: string, active?: number) => void
  close: () => void
}>((set) => ({
  open: null,
  show: (messageKey, active = 1) => set({ open: { messageKey, active } }),
  close: () => set({ open: null }),
}))
