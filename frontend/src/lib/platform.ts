const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform)

/** Label for the primary modifier key on this platform. */
export const MOD = isMac ? "⌘" : "Ctrl"
