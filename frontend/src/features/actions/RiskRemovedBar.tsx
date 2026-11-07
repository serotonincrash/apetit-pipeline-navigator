const WIDTH = 96;
const HEIGHT = 8;

/** A bar for one action's risk removed, drawn against the largest value in the table. */
export function RiskRemovedBar({ value, max }: { value: number; max: number }) {
  const length = max > 0 ? Math.max(0, Math.min(1, value / max)) * WIDTH : 0;
  return (
    <svg width={WIDTH} height={HEIGHT} aria-hidden="true" className="inline-block">
      <rect width={WIDTH} height={HEIGHT} className="fill-muted" />
      <rect width={length} height={HEIGHT} className="fill-muted-foreground" />
    </svg>
  );
}
