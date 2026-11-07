import type { TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "min-h-16 w-full rounded-md border bg-background px-2 py-1.5 text-sm placeholder:text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}
