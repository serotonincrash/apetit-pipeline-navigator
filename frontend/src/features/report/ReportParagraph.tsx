import type { Insight, Metric, ReportParagraph as ParagraphData } from "@/api/generated/model";
import { ParagraphSources } from "./ParagraphSources";
import { citedMetricIds } from "./reportTokens";
import { TokenText } from "./TokenText";

interface ReportParagraphProps {
  paragraph: ParagraphData;
  /** The section above, so a second heading in one section reads as a sub-heading. */
  previousSection: string | undefined;
  metrics: Record<string, Metric>;
  insights: Insight[];
  /** True while the assistant's text has not been approved. */
  suggested: boolean;
}

type Block = { kind: "text"; lines: string[] } | { kind: "list"; lines: string[] };

/** Lines that start with "- " form a list. Everything else is a paragraph. */
function blocksOf(text: string): Block[] {
  const blocks: Block[] = [];
  for (const line of text.split("\n")) {
    const kind = line.startsWith("- ") ? "list" : "text";
    const last = blocks[blocks.length - 1];
    const body = kind === "list" ? line.slice(2) : line;
    if (last?.kind === kind) last.lines.push(body);
    else blocks.push({ kind, lines: [body] });
  }
  return blocks;
}

export function ReportParagraph({
  paragraph,
  previousSection,
  metrics,
  insights,
  suggested,
}: ReportParagraphProps) {
  const isSub = previousSection === paragraph.section;
  const Heading = isSub ? "h3" : "h2";
  const agentText = suggested && paragraph.call_id !== null;
  return (
    <section>
      {paragraph.heading ? (
        <Heading className={isSub ? "mb-2 mt-6 font-semibold" : "mb-2 mt-10 text-lg font-semibold"}>
          {paragraph.heading}
        </Heading>
      ) : null}
      {agentText ? (
        <p className="text-xs text-muted-foreground">Suggested by the assistant</p>
      ) : null}
      <div className="space-y-2">
        {blocksOf(paragraph.text).map((block, index) =>
          block.kind === "list" ? (
            // biome-ignore lint/suspicious/noArrayIndexKey: blocks are built from fixed text
            <ul key={index} className="list-disc space-y-1 pl-5">
              {block.lines.map((line, position) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: lines repeat, and the list is fixed
                <li key={position} className="break-words">
                  <TokenText text={line} metrics={metrics} />
                </li>
              ))}
            </ul>
          ) : (
            // biome-ignore lint/suspicious/noArrayIndexKey: blocks are built from fixed text
            <p key={index} className="break-words">
              <TokenText text={block.lines.join(" ")} metrics={metrics} insights={insights} />
            </p>
          ),
        )}
      </div>
      <ParagraphSources metricIds={citedMetricIds(paragraph.text, insights)} />
    </section>
  );
}
