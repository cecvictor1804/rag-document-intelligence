import { FileText } from "lucide-react";

import { Chat } from "@/components/chat";
import { MetricsPanel } from "@/components/metrics-panel";
import { ThemeToggle } from "@/components/theme-toggle";
import { UserMenu } from "@/components/user-menu";

// The header reflects the signed-in user (when auth is on), so render per-request
// rather than prerendering a static, user-less page.
export const dynamic = "force-dynamic";

export default function Home() {
  return (
    <div className="relative flex h-dvh flex-col overflow-hidden">
      {/* Ambient drifting glow blobs */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 -z-10 overflow-hidden"
      >
        <div className="blob absolute -left-1/4 -top-[10%] size-[40rem] rounded-full bg-[var(--glow)] blur-3xl" />
        <div className="blob absolute -right-1/4 -bottom-[15%] size-[36rem] rounded-full bg-[var(--glow)] blur-3xl [animation-delay:-9s]" />
      </div>

      <header className="sticky top-0 z-10 border-b bg-background/70 backdrop-blur-md">
        <div className="mx-auto flex w-full max-w-3xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-primary/60 text-primary-foreground shadow-sm">
              <FileText className="size-4" />
            </div>
            <span className="font-semibold tracking-tight">Internal Docs AI</span>
          </div>
          <div className="flex items-center gap-1">
            <MetricsPanel />
            <ThemeToggle />
            <UserMenu />
          </div>
        </div>
      </header>

      <Chat />
    </div>
  );
}
