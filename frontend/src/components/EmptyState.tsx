import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  children?: ReactNode;
}

export function EmptyState({ title, children }: EmptyStateProps) {
  return (
    <div className="border-y py-10 text-center">
      <p className="font-medium">{title}</p>
      {children ? <div className="mt-3 text-muted-foreground">{children}</div> : null}
    </div>
  );
}
