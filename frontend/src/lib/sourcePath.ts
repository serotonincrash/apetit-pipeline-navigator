import type { MetricSource, RunDetail, StepRun } from "@/api/generated/model";

export interface PathNode {
  step: StepRun;
  /** The tables of this step that the metric's lineage names. */
  tables: MetricSource[];
}

/**
 * The steps behind a number: those that wrote the lineage tables, and every step whose output
 * they read, back to the first. Latest step first.
 */
export function buildPath(run: RunDetail, sources: MetricSource[]): PathNode[] {
  const producer = new Map<string, StepRun>();
  for (const step of run.steps) {
    for (const artifactId of step.output_artifacts) producer.set(artifactId, step);
  }
  const byStepRun = new Map(run.steps.map((step) => [step.step_run_id, step]));

  const included = new Map<string, StepRun>();
  const queue: StepRun[] = [];
  for (const source of sources) {
    const step = byStepRun.get(source.artifact.step_run_id);
    if (step && !included.has(step.step_run_id)) {
      included.set(step.step_run_id, step);
      queue.push(step);
    }
  }
  for (let step = queue.shift(); step; step = queue.shift()) {
    for (const artifactId of step.input_artifacts) {
      const parent = producer.get(artifactId);
      if (parent && !included.has(parent.step_run_id)) {
        included.set(parent.step_run_id, parent);
        queue.push(parent);
      }
    }
  }

  return [...included.values()]
    .sort((a, b) => b.position - a.position)
    .map((step) => ({
      step,
      tables: sources.filter((source) => source.artifact.step_run_id === step.step_run_id),
    }));
}
