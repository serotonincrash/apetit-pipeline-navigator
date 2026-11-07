import type { InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-8 w-full rounded-md border bg-background px-2 text-sm placeholder:text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}
