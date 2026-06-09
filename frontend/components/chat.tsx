"use client";

import * as React from "react";

import { Composer } from "@/components/composer";
import { EmptyState } from "@/components/empty-state";
import { Message } from "@/components/message";
import { useChat } from "@/lib/use-chat";

export function Chat() {
  const { messages, isStreaming, send, stop } = useChat();
  const bottomRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const empty = messages.length === 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 py-8">
          {empty ? (
            <div className="flex min-h-[50vh] items-center justify-center">
              <EmptyState onPick={send} />
            </div>
          ) : (
            <div className="flex flex-col gap-6">
              {messages.map((m) => (
                <Message key={m.id} message={m} />
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>
      </div>

      <div className="sticky bottom-0 bg-gradient-to-t from-background via-background to-transparent pb-4 pt-2">
        <div className="mx-auto w-full max-w-3xl px-4">
          <Composer onSend={send} onStop={stop} isStreaming={isStreaming} />
          <p className="mt-2 text-center text-xs text-muted-foreground">
            Answers are grounded in your docs and cite their sources.
          </p>
        </div>
      </div>
    </div>
  );
}
