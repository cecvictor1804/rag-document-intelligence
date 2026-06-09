"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { Sparkles, ThumbsDown, ThumbsUp, User } from "lucide-react";
import { toast } from "sonner";

import { CitationChip, Sources } from "@/components/citation";
import { ModelBadge } from "@/components/model-badge";
import { sendFeedback } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";
import { cn } from "@/lib/utils";

function renderWithCitations(content: string): React.ReactNode[] {
  return content.split(/(\[\d+\])/g).map((part, i) => {
    const m = part.match(/^\[(\d+)\]$/);
    if (m) return <CitationChip key={i} n={Number(m[1])} />;
    return <React.Fragment key={i}>{part}</React.Fragment>;
  });
}

function Feedback({ message }: { message: ChatMessage }) {
  const [rated, setRated] = React.useState<1 | -1 | null>(null);

  async function rate(rating: 1 | -1) {
    if (rated) return;
    setRated(rating);
    try {
      await sendFeedback({
        query: "", // server records the answer; query threading is a follow-up
        answer: message.content,
        rating,
      });
      toast.success(rating === 1 ? "Thanks for the feedback!" : "Thanks — we'll improve.");
    } catch {
      setRated(null);
      toast.error("Couldn't save feedback.");
    }
  }

  return (
    <div className="mt-3 flex items-center gap-1">
      <button
        aria-label="Helpful"
        onClick={() => rate(1)}
        className={cn(
          "rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
          rated === 1 && "bg-primary/15 text-primary",
        )}
      >
        <ThumbsUp className="size-3.5" />
      </button>
      <button
        aria-label="Not helpful"
        onClick={() => rate(-1)}
        className={cn(
          "rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
          rated === -1 && "bg-destructive/15 text-destructive",
        )}
      >
        <ThumbsDown className="size-3.5" />
      </button>
    </div>
  );
}

export function Message({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className={cn("flex gap-3", isUser && "flex-row-reverse")}
    >
      <div
        className={cn(
          "flex size-8 shrink-0 items-center justify-center rounded-full",
          isUser
            ? "bg-secondary text-secondary-foreground"
            : "bg-gradient-to-br from-primary to-primary/60 text-primary-foreground shadow-sm",
        )}
      >
        {isUser ? <User className="size-4" /> : <Sparkles className="size-4" />}
      </div>

      <div className={cn("min-w-0 max-w-[min(46rem,85%)]", isUser && "text-right")}>
        <div
          className={cn(
            "inline-block rounded-2xl px-4 py-2.5 text-left text-sm leading-relaxed",
            isUser
              ? "bg-primary text-primary-foreground"
              : "border bg-card/70 backdrop-blur-sm",
            message.error && "border-destructive/40 bg-destructive/10 text-destructive",
          )}
        >
          {message.pending && !message.content ? (
            <span className="flex items-center gap-1.5 text-muted-foreground">
              <span className="size-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.3s]" />
              <span className="size-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.15s]" />
              <span className="size-1.5 animate-bounce rounded-full bg-current" />
            </span>
          ) : (
            <span className="whitespace-pre-wrap break-words">
              {isUser ? message.content : renderWithCitations(message.content)}
              {message.pending && <span className="caret-blink ml-0.5">▍</span>}
            </span>
          )}
        </div>

        {!isUser && !message.pending && (
          <>
            {message.citations && <Sources citations={message.citations} />}
            <div className="mt-2 flex items-center gap-2">
              <ModelBadge model={message.meta?.model} />
              {!message.error && message.content && <Feedback message={message} />}
            </div>
          </>
        )}
      </div>
    </motion.div>
  );
}
