import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { getGetRunQueryKey } from "@/api/generated/client";
import type { RunEvent } from "@/api/generated/model";

export interface LiveSection {
  name: string;
  annotation: string;
  seconds: number | null;
}

export type LiveSections = Record<string, LiveSection[]>;

function apply(sections: LiveSections, event: RunEvent): LiveSections {
  if (event.type === "section.started") {
    const { step, section, annotation } = event.payload;
    const known = sections[step] ?? [];
    if (known.some((item) => item.name === section)) return sections;
    return { ...sections, [step]: [...known, { name: section, annotation, seconds: null }] };
  }
  if (event.type === "section.finished") {
    const { step, section, annotation, seconds } = event.payload;
    const known = sections[step] ?? [];
    const found = known.some((item) => item.name === section);
    const next = found
      ? known.map((item) => (item.name === section ? { ...item, seconds } : item))
      : [...known, { name: section, annotation, seconds }];
    return { ...sections, [step]: next };
  }
  return sections;
}

/**
 * Follows a run's events. The browser reconnects by itself and sends the last event id, so the
 * stream resumes where it stopped. Each event refreshes the run so steps update as they finish.
 */
export function useRunEvents(runId: string): LiveSections {
  const queryClient = useQueryClient();
  const [sections, setSections] = useState<LiveSections>({});

  useEffect(() => {
    setSections({});
    const source = new EventSource(`/api/runs/${runId}/events`);
    source.onmessage = (message: MessageEvent<string>) => {
      const event = JSON.parse(message.data) as RunEvent;
      setSections((current) => apply(current, event));
      if (event.type !== "section.started" && event.type !== "section.finished") {
        void queryClient.invalidateQueries({ queryKey: getGetRunQueryKey(runId) });
      }
      if (event.type === "run.finished") source.close();
    };
    return () => source.close();
  }, [runId, queryClient]);

  return sections;
}
