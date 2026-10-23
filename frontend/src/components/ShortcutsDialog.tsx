import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { MOD } from "@/lib/platform"


const SHORTCUTS: [string, string[]][] = [
  ["New chat", [MOD, "Shift", "O"]],
  ["Search chats", [MOD, "K"]],
  ["Focus the message box", ["/"]],
  ["Stop generating", ["Esc"]],
  ["New line in a message", ["Shift", "Enter"]],
  ["Show keyboard shortcuts", [MOD, "/"]],
]

export function ShortcutsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription className="sr-only">Keys for common actions</DialogDescription>
        </DialogHeader>
        <dl className="divide-y">
          {SHORTCUTS.map(([label, keys]) => (
            <div key={label} className="flex items-center justify-between py-2.5 text-sm">
              <dt>{label}</dt>
              <dd className="flex gap-1">
                {keys.map((k) => (
                  <kbd key={k} className="min-w-6 rounded-md border bg-muted px-1.5 py-0.5 text-center font-sans text-xs">
                    {k}
                  </kbd>
                ))}
              </dd>
            </div>
          ))}
        </dl>
      </DialogContent>
    </Dialog>
  )
}
