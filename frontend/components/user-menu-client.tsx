"use client";

import { LogOut } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

export function UserMenuClient({ email, name }: { email: string; name: string }) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);
  const initial = (name || email).trim().charAt(0).toUpperCase() || "?";

  React.useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        className="flex size-8 items-center justify-center rounded-full bg-gradient-to-br from-primary to-primary/60 text-xs font-semibold text-primary-foreground shadow-sm transition-transform hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60"
      >
        {initial}
      </button>

      <div
        role="menu"
        className={cn(
          "absolute right-0 top-10 z-20 w-56 origin-top-right overflow-hidden rounded-lg border bg-popover p-1 shadow-lg transition-all",
          open ? "scale-100 opacity-100" : "pointer-events-none scale-95 opacity-0",
        )}
      >
        <div className="px-3 py-2">
          {name && <p className="truncate text-sm font-medium">{name}</p>}
          <p className="truncate text-xs text-muted-foreground">{email}</p>
        </div>
        <div className="my-1 h-px bg-border" />
        <form action="/api/auth/logout" method="post">
          <button
            type="submit"
            role="menuitem"
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors hover:bg-accent hover:text-accent-foreground"
          >
            <LogOut className="size-4" />
            Sign out
          </button>
        </form>
      </div>
    </div>
  );
}
