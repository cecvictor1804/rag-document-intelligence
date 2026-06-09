import { FileText } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { hostedDomain } from "@/lib/auth/config";
import { cn } from "@/lib/utils";

const ERRORS: Record<string, string> = {
  invalid_state: "Your sign-in session expired. Please try again.",
  auth_failed: "We couldn't sign you in with that account.",
};

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  const message = error ? (ERRORS[error] ?? "Sign-in failed. Please try again.") : null;

  return (
    <div className="relative flex min-h-dvh items-center justify-center overflow-hidden px-4">
      {/* Ambient drifting glow blobs (matches the chat page). */}
      <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
        <div className="blob absolute -left-1/4 -top-[10%] size-[40rem] rounded-full bg-[var(--glow)] blur-3xl" />
        <div className="blob absolute -right-1/4 -bottom-[15%] size-[36rem] rounded-full bg-[var(--glow)] blur-3xl [animation-delay:-9s]" />
      </div>

      <div className="w-full max-w-sm rounded-2xl border bg-background/70 p-8 text-center shadow-sm backdrop-blur-md">
        <div className="mx-auto mb-5 flex size-12 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-primary/60 text-primary-foreground shadow-sm">
          <FileText className="size-6" />
        </div>
        <h1 className="text-xl font-semibold tracking-tight">Internal Docs AI</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Sign in with your{hostedDomain ? ` ${hostedDomain}` : " company"} Google
          account to ask questions across your internal documentation.
        </p>

        {message && (
          <p className="mt-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {message}
          </p>
        )}

        <a
          href="/api/auth/login"
          className={cn(buttonVariants({ variant: "outline" }), "mt-6 w-full gap-3")}
        >
          <GoogleIcon />
          Continue with Google
        </a>

        <p className="mt-6 text-xs text-muted-foreground">
          Access is restricted to authorized accounts.
        </p>
      </div>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden>
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1Z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23Z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84Z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84C6.71 7.3 9.14 5.38 12 5.38Z"
      />
    </svg>
  );
}
