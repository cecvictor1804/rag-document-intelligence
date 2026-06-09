"use client";

import { motion } from "framer-motion";
import { ExternalLink } from "lucide-react";

import type { Citation } from "@/lib/types";
import { cn } from "@/lib/utils";

export function CitationChip({ n }: { n: number }) {
  return (
    <sup className="mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded bg-primary/15 px-1 align-super text-[10px] font-semibold text-primary">
      {n}
    </sup>
  );
}

function SourceCard({ c, index }: { c: Citation; index: number }) {
  const hasLink = Boolean(c.source_url);
  const inner = (
    <>
      <div className="flex items-center gap-2">
        <span className="flex size-5 shrink-0 items-center justify-center rounded-md bg-primary/15 text-[11px] font-semibold text-primary">
          {c.n}
        </span>
        <span className="truncate text-sm font-medium">{c.title}</span>
        {hasLink && (
          <ExternalLink className="ml-auto size-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
        )}
      </div>
      {c.section && (
        <div className="mt-0.5 truncate text-xs text-muted-foreground">
          {c.section}
        </div>
      )}
      <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
        {c.snippet}
      </p>
    </>
  );

  const className = cn(
    "group block rounded-xl border bg-card/60 p-3 backdrop-blur-sm transition-all",
    hasLink && "hover:border-primary/40 hover:bg-card hover:shadow-sm",
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.2 }}
    >
      {hasLink ? (
        <a href={c.source_url} target="_blank" rel="noreferrer" className={className}>
          {inner}
        </a>
      ) : (
        <div className={className}>{inner}</div>
      )}
    </motion.div>
  );
}

export function Sources({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;
  return (
    <div className="mt-4">
      <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Sources
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {citations.map((c, i) => (
          <SourceCard key={`${c.n}-${c.doc_id}`} c={c} index={i} />
        ))}
      </div>
    </div>
  );
}
