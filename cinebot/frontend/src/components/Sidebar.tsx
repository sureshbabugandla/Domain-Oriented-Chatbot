/**
 * Narrow sidebar: identity, "new reel" button, connection status, and
 * sign-out. History list is a future addition — the GET /sessions
 * endpoint isn't implemented in Milestone 6, so I leave a placeholder
 * rather than show fake data.
 */

import { Film, Plus, LogOut, Circle } from "lucide-react";
import { useStore } from "@/lib/store";
import { Sprocket } from "./Sprocket";
import { cn } from "@/lib/utils";

interface Props {
  wsStatus: "idle" | "connecting" | "open" | "closed" | "error";
  onNewChat: () => void;
}

const statusCopy: Record<Props["wsStatus"], { label: string; tone: string }> = {
  idle:       { label: "idle",        tone: "text-muted-foreground" },
  connecting: { label: "connecting",  tone: "text-amber-400" },
  open:       { label: "live",        tone: "text-emerald-400" },
  closed:     { label: "disconnected", tone: "text-muted-foreground" },
  error:      { label: "error",       tone: "text-destructive" },
};

export function Sidebar({ wsStatus, onNewChat }: Props) {
  const { email, signOut } = useStore();
  const { label, tone } = statusCopy[wsStatus];

  return (
    <aside className="hidden w-[260px] shrink-0 flex-col border-r border-border bg-card/40 md:flex">
      {/* Brand */}
      <div className="px-5 pb-4 pt-6">
        <div className="flex items-center gap-2">
          <Film className="h-5 w-5 text-accent" strokeWidth={1.5} />
          <span className="font-display text-xl tracking-tight">CineBot</span>
        </div>
        <p className="mt-1 text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
          in conversation, in colour
        </p>
      </div>

      <Sprocket className="mx-5 mb-4" count={18} />

      {/* Actions */}
      <div className="px-3">
        <button
          type="button"
          onClick={onNewChat}
          className={cn(
            "flex w-full items-center gap-2 rounded-sm border border-border bg-background/50 px-3 py-2",
            "text-sm text-foreground/90 transition-colors",
            "hover:border-accent hover:text-accent",
          )}
        >
          <Plus className="h-3.5 w-3.5" />
          New reel
        </button>
      </div>

      {/* History placeholder */}
      <div className="mt-5 flex-1 overflow-y-auto px-5">
        <h2 className="mb-2 text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
          Recent
        </h2>
        <p className="text-sm italic text-muted-foreground/80">
          Your past conversations will appear here.
        </p>
      </div>

      {/* Footer */}
      <div className="border-t border-border px-5 py-4 text-sm">
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em]">
          <Circle className={cn("h-2 w-2", tone)} fill="currentColor" />
          <span className="text-muted-foreground">{label}</span>
        </div>
        <div className="mt-3 flex items-center justify-between">
          <span className="truncate text-sm text-foreground/80" title={email ?? ""}>
            {email ?? "anonymous"}
          </span>
          <button
            type="button"
            onClick={signOut}
            aria-label="Sign out"
            className="inline-flex h-7 w-7 items-center justify-center rounded-sm text-muted-foreground hover:bg-secondary"
          >
            <LogOut className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </aside>
  );
}
