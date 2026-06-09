"use client";

import * as React from "react";
import { ArrowUp, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export function Composer({
  onSend,
  onStop,
  isStreaming,
}: {
  onSend: (text: string) => void;
  onStop: () => void;
  isStreaming: boolean;
}) {
  const [value, setValue] = React.useState("");
  const ref = React.useRef<HTMLTextAreaElement>(null);

  // Auto-grow up to a cap.
  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [value]);

  function submit() {
    const text = value.trim();
    if (!text || isStreaming) return;
    onSend(text);
    setValue("");
  }

  return (
    <div className="rounded-2xl border bg-card/80 p-2 shadow-lg shadow-black/5 backdrop-blur-md transition-colors focus-within:border-primary/50">
      <div className="flex items-end gap-2">
        <Textarea
          ref={ref}
          rows={1}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="Ask about internal documentation…"
          className="max-h-[180px] flex-1 py-2"
          aria-label="Message"
        />
        {isStreaming ? (
          <Button size="icon" variant="secondary" onClick={onStop} aria-label="Stop">
            <Square className="size-4" />
          </Button>
        ) : (
          <Button
            size="icon"
            onClick={submit}
            disabled={!value.trim()}
            aria-label="Send"
          >
            <ArrowUp className="size-4" />
          </Button>
        )}
      </div>
    </div>
  );
}
