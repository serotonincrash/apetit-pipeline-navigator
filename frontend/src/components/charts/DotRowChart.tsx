import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { scenarioColour, themeColour } from "@/lib/theme";

export interface DotPoint {
  rowIndex: number;
  value: number;
  scenario: string;
  metricId: string;
  /** The value as the tooltip shows it. */
  text: string;
}

interface DotRowChartProps {
  rowLabels: string[];
  points: DotPoint[];
  formatValue: (value: number) => string;
  onPointClick: (metricId: string) => void;
}

interface ShapeProps {
  cx?: number;
  cy?: number;
  payload?: DotPoint;
}

const ROW_HEIGHT = 30;

// The row lines are drawn by Scatter itself; this keeps the line series from drawing dots.
const renderNothing = () => <g />;

/** One row per item, a dot per scenario, joined by a thin line. The shared dot-and-line chart. */
export function DotRowChart({ rowLabels, points, formatValue, onPointClick }: DotRowChartProps) {
  const line = themeColour("border");
  const rows = rowLabels.map((_, index) => ({
    index,
    points: points.filter((point) => point.rowIndex === index).sort((a, b) => a.value - b.value),
  }));
  const scenarios = [...new Set(points.map((point) => point.scenario))];

  const renderDot = (props: ShapeProps) => {
    const { cx, cy, payload } = props;
    if (cx === undefined || cy === undefined || !payload) return <g />;
    const colour = scenarioColour(payload.scenario);
    const hollow = payload.scenario === "baseline";
    return (
      // biome-ignore lint/a11y/useSemanticElements: an SVG dot cannot be a button element
      <circle
        cx={cx}
        cy={cy}
        r={6}
        fill={hollow ? themeColour("background") : colour}
        stroke={colour}
        strokeWidth={2}
        className="cursor-pointer"
        role="button"
        tabIndex={0}
        aria-label={`${payload.text}. Show sources`}
        onClick={() => onPointClick(payload.metricId)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") onPointClick(payload.metricId);
        }}
      />
    );
  };

  return (
    <ResponsiveContainer width="100%" height={rowLabels.length * ROW_HEIGHT + 48}>
      <ScatterChart margin={{ top: 8, right: 24, bottom: 8, left: 8 }}>
        <CartesianGrid horizontal={false} stroke={line} />
        <XAxis
          type="number"
          dataKey="value"
          tickFormatter={formatValue}
          domain={[0, "auto"]}
          stroke={themeColour("muted-foreground")}
        />
        <YAxis
          type="number"
          dataKey="rowIndex"
          reversed
          width={230}
          ticks={rowLabels.map((_, index) => index)}
          domain={[-0.5, rowLabels.length - 0.5]}
          tickFormatter={(index: number) => rowLabels[index] ?? ""}
          interval={0}
          axisLine={false}
          tickLine={false}
          stroke={themeColour("foreground")}
        />
        <Tooltip
          cursor={false}
          content={({ payload }) => {
            const point = payload?.[0]?.payload as DotPoint | undefined;
            if (!point) return null;
            return (
              <div className="border bg-background px-2 py-1">
                <p className="font-medium">{rowLabels[point.rowIndex]}</p>
                <p>{point.text}</p>
              </div>
            );
          }}
        />
        {rows.map((row) => (
          <Scatter
            key={`line-${row.index}`}
            data={row.points}
            line={{ stroke: line, strokeWidth: 1.5 }}
            shape={renderNothing}
            isAnimationActive={false}
            legendType="none"
          />
        ))}
        {scenarios.map((scenario) => (
          <Scatter
            key={scenario}
            name={scenario}
            data={points.filter((point) => point.scenario === scenario)}
            shape={renderDot}
            isAnimationActive={false}
          />
        ))}
      </ScatterChart>
    </ResponsiveContainer>
  );
}
