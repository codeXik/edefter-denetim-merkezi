import type { ReactNode } from "react";

type BadgeTone = "ok" | "info" | "warning" | "danger" | "neutral";

interface BadgeProps {
  children: ReactNode;
  tone: BadgeTone;
}

export function Badge({ children, tone }: BadgeProps) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
