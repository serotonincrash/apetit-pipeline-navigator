import { Button } from "@/components/ui/button";

interface ErrorStateProps {
  title: string;
  message?: string;
  runId?: string;
  onRetry?: () => void;
}

export function ErrorState({ title, message, runId, onRetry }: ErrorStateProps) {
  return (
    <div className="border-y border-danger py-6" role="alert">
      <p className="font-medium text-danger">{title}</p>
      {message ? <p className="mt-1">{message}</p> : null}
      <div className="mt-3 flex items-center gap-3">
        {onRetry ? (
          <Button size="sm" onClick={onRetry}>
            Try again
          </Button>
        ) : null}
        {runId ? (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => void navigator.clipboard?.writeText(runId)}
          >
            Copy run id {runId}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
