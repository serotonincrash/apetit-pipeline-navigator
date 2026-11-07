import type { SelectHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn("h-8 rounded-md border bg-background px-2 text-sm", className)}
      {...props}
    />
  );
}
