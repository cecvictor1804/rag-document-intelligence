import { Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";

const LABELS: Record<string, string> = {
  "claude-haiku-4-5": "Haiku",
  "claude-sonnet-4-6": "Sonnet",
  "claude-opus-4-8": "Opus",
};

export function ModelBadge({ model }: { model?: string | null }) {
  if (!model) return null;
  const label = LABELS[model] ?? model;
  return (
    <Badge variant="muted" title={`Answered by ${model}`}>
      <Sparkles className="size-3" />
      {label}
    </Badge>
  );
}
