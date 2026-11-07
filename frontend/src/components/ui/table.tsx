import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export function Table({ className, ...props }: ComponentProps<"table">) {
  return <table className={cn("w-full border-collapse text-sm", className)} {...props} />;
}

export function TableHead({ className, ...props }: ComponentProps<"thead">) {
  return <thead className={cn("border-b bg-muted text-left", className)} {...props} />;
}

export function TableBody(props: ComponentProps<"tbody">) {
  return <tbody {...props} />;
}

export function TableRow({ className, ...props }: ComponentProps<"tr">) {
  return <tr className={cn("border-b last:border-b-0", className)} {...props} />;
}

interface CellProps {
  numeric?: boolean;
}

export function TableHeaderCell({
  className,
  numeric,
  ...props
}: ComponentProps<"th"> & CellProps) {
  return (
    <th
      className={cn(
        "whitespace-nowrap px-2.5 py-1.5 text-xs font-medium text-muted-foreground",
        numeric ? "text-right" : "text-left",
        className,
      )}
      {...props}
    />
  );
}

export function TableCell({ className, numeric, ...props }: ComponentProps<"td"> & CellProps) {
  return (
    <td
      className={cn("px-2.5 py-1.5 align-top", numeric && "text-right tabular-nums", className)}
      {...props}
    />
  );
}
