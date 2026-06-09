"use client";

import { motion } from "framer-motion";
import { FileText, Plane, ShieldCheck } from "lucide-react";

const EXAMPLES = [
  { icon: Plane, text: "How much can I expense for meals per day?" },
  { icon: FileText, text: "How do I set up my account on my first day?" },
  { icon: ShieldCheck, text: "What do I need to sign in to the VPN?" },
];

export function EmptyState({ onPick }: { onPick: (q: string) => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="mx-auto flex max-w-2xl flex-col items-center text-center"
    >
      <div className="mb-5 flex size-14 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-primary/60 text-primary-foreground shadow-lg shadow-primary/20">
        <FileText className="size-7" />
      </div>
      <h1 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">
        Ask your internal documentation
      </h1>
      <p className="mt-2 text-pretty text-sm text-muted-foreground sm:text-base">
        Grounded, cited answers from your company docs — never a guess.
      </p>

      <div className="mt-7 grid w-full gap-2 sm:grid-cols-3">
        {EXAMPLES.map(({ icon: Icon, text }, i) => (
          <motion.button
            key={text}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 + i * 0.06 }}
            onClick={() => onPick(text)}
            className="group flex h-full flex-col gap-2 rounded-xl border bg-card/60 p-3 text-left text-sm backdrop-blur-sm transition-all hover:border-primary/40 hover:bg-card hover:shadow-sm"
          >
            <Icon className="size-4 text-primary" />
            <span className="text-muted-foreground transition-colors group-hover:text-foreground">
              {text}
            </span>
          </motion.button>
        ))}
      </div>
    </motion.div>
  );
}
