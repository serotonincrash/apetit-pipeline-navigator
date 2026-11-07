import { Skeleton } from "@/components/ui/skeleton";

export function TableSkeleton({ rows = 8 }: { rows?: number }) {
  const keys = Array.from({ length: rows }, (_, index) => `row-${index}`);
  return (
    <div className="flex flex-col gap-2 py-2" aria-hidden="true">
      {keys.map((key) => (
        <Skeleton key={key} className="h-5 w-full" />
      ))}
    </div>
  );
}
