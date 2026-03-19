import { AnalysisData, ChatMessage } from "@/types/chat";
import type { UserRole } from "@/components/RoleToggle";

export interface ChatThread {
  id: string;
  title: string;
  role: UserRole;
  messages: ChatMessage[];
  updatedAt: number;
}

export function createEmptyThread(role: UserRole): ChatThread {
  return {
    id: crypto.randomUUID(),
    title: "New analysis",
    role,
    messages: [],
    updatedAt: Date.now(),
  };
}

export function getThreadTitle(input: string) {
  return input.length > 42 ? `${input.slice(0, 42)}…` : input;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

const MAX_PLOT_POINTS = 1500;

function sampleIndexes(length: number): number[] {
  if (length <= 0) {
    return [];
  }

  if (length <= MAX_PLOT_POINTS) {
    return Array.from({ length }, (_, index) => index);
  }

  const step = Math.ceil(length / MAX_PLOT_POINTS);
  const indexes: number[] = [];
  for (let index = 0; index < length; index += step) {
    indexes.push(index);
  }
  if (indexes[indexes.length - 1] !== length - 1) {
    indexes.push(length - 1);
  }
  return indexes;
}

function formatValue(value: number): string {
  if (Math.abs(value) < 0.001 || Math.abs(value) >= 100_000) {
    return value.toExponential(4);
  }
  return value.toPrecision(5);
}

function buildValueArrayAnalysis(message: ChatMessage): AnalysisData[] | null {
  const toolCall = [...(message.toolCalls ?? [])]
    .reverse()
    .find((entry) => entry.name === "db_get_test_value_arrays");

  if (!toolCall || typeof toolCall.result !== "object" || toolCall.result === null) {
    return null;
  }

  const result = toolCall.result as Record<string, unknown>;
  const rawValueArrays = result.valueArrays;
  if (!Array.isArray(rawValueArrays)) {
    return null;
  }

  const seriesSummaries = Array.isArray(result.seriesSummaries)
    ? result.seriesSummaries
    : [];

  const plottedArrays = rawValueArrays.map((entry) =>
    Array.isArray(entry)
      ? entry.map((value) => (isFiniteNumber(value) ? value : null))
      : [],
  );

  const longestSeries = plottedArrays.reduce(
    (max, values) => Math.max(max, values.length),
    0,
  );
  const sampledIndexes = sampleIndexes(longestSeries);

  const points = sampledIndexes.map((index) => {
    const point: Record<string, string | number | null> = { index };
    plottedArrays.forEach((values, seriesIndex) => {
      point[`series_${seriesIndex + 1}`] = values[index] ?? null;
    });
    return point;
  });

  const testId = typeof result.testId === "string" ? result.testId : "Unknown";

  return [
    {
      type: "chart",
      title: "Test value arrays",
      subtitle:
        sampledIndexes.length === longestSeries
          ? `Test ${testId}. Each returned value array is shown as a separate line over sample index.`
          : `Test ${testId}. The frontend deterministically samples ${sampledIndexes.length} of ${longestSeries} points for plotting while preserving the raw array for the tool result.`,
      data: {
        kind: "line",
        xKey: "index",
        yAxisLabel: "Value",
        points,
        series: plottedArrays.map((_, seriesIndex) => {
          const summary = seriesSummaries[seriesIndex];
          const label =
            summary && typeof summary === "object" && typeof summary.label === "string"
              ? summary.label
              : `Result ${seriesIndex + 1}`;

          return {
            key: `series_${seriesIndex + 1}`,
            label,
          };
        }),
      },
    },
  ];
}

function buildValueColumnsAnalysis(message: ChatMessage): AnalysisData[] | null {
  const toolCall = [...(message.toolCalls ?? [])]
    .reverse()
    .find((entry) => entry.name === "db_get_test_value_columns");

  if (!toolCall || typeof toolCall.result !== "object" || toolCall.result === null) {
    return null;
  }

  const result = toolCall.result as Record<string, unknown>;
  const rawValueColumns = result.valueColumns;
  if (!Array.isArray(rawValueColumns)) {
    return null;
  }

  const seriesSummaries = Array.isArray(result.seriesSummaries)
    ? result.seriesSummaries
    : [];

  const plottedColumns = rawValueColumns
    .map((entry) =>
      typeof entry === "object" && entry !== null
        ? (entry as Record<string, unknown>)
        : null,
    )
    .filter((entry): entry is Record<string, unknown> => entry !== null)
    .map((entry, index) => {
      const summary = seriesSummaries[index];
      const summaryLabel =
        summary && typeof summary === "object" && typeof summary.label === "string"
          ? summary.label
          : null;

      return {
        label:
          typeof summaryLabel === "string" && summaryLabel.trim().length > 0
            ? summaryLabel
            : typeof entry.name === "string" && entry.name.trim().length > 0
            ? entry.name
            : typeof entry.childId === "string" && entry.childId.trim().length > 0
            ? entry.childId
            : "Value column",
        values: Array.isArray(entry.values)
          ? entry.values.map((value) => (isFiniteNumber(value) ? value : null))
          : [],
        unitTableId:
          typeof entry.unitTableId === "string" ? entry.unitTableId : undefined,
      };
    })
    .filter((entry) => entry.values.length > 0);

  if (plottedColumns.length === 0) {
    return null;
  }

  const longestSeries = plottedColumns.reduce(
    (max, column) => Math.max(max, column.values.length),
    0,
  );
  const sampledIndexes = sampleIndexes(longestSeries);

  const points = sampledIndexes.map((index) => {
    const point: Record<string, string | number | null> = { index };
    plottedColumns.forEach((column, seriesIndex) => {
      point[`series_${seriesIndex + 1}`] = column.values[index] ?? null;
    });
    return point;
  });

  const testId = typeof result.testId === "string" ? result.testId : "Unknown";
  const sharedUnitTableId =
    plottedColumns.length > 0 &&
    plottedColumns.every((column) => column.unitTableId === plottedColumns[0].unitTableId)
      ? plottedColumns[0].unitTableId
      : undefined;

  const signalLabel = plottedColumns[0]?.label ?? "Value columns";

  const allValues = plottedColumns
    .flatMap((col) => col.values)
    .filter((v): v is number => v !== null && isFiniteNumber(v));

  const maxVal = allValues.length > 0 ? Math.max(...allValues) : null;
  const minVal = allValues.length > 0 ? Math.min(...allValues) : null;

  return [
    {
      type: "stats",
      title: "Value column plot summary",
      data: [
        { label: "Signal", value: signalLabel, delta: "connected" },
        { label: "Points", value: String(longestSeries), delta: "total samples" },
        { label: "Max", value: maxVal !== null ? formatValue(maxVal) : "—", delta: "breakpoint" },
        { label: "Min", value: minVal !== null ? formatValue(minVal) : "—", delta: "lowest recorded" },
      ],
    },
    {
      type: "chart",
      title: "Test value columns",
      subtitle:
        sampledIndexes.length === longestSeries
          ? `Test ${testId}. Each returned value column is shown as a separate line over sample index.`
          : `Test ${testId}. The frontend deterministically samples ${sampledIndexes.length} of ${longestSeries} points for plotting while preserving the raw values in the tool result.`,
      data: {
        kind: "line",
        xKey: "index",
        yAxisLabel: sharedUnitTableId ?? "Value",
        points,
        series: plottedColumns.map((column, seriesIndex) => ({
          key: `series_${seriesIndex + 1}`,
          label: column.label,
        })),
      },
    },
  ];
}

export function deriveAnalysisData(messages: ChatMessage[]): AnalysisData[] {
  const latestAssistantMessage = [...messages]
    .reverse()
    .find((message) => message.role === "assistant");

  if (!latestAssistantMessage) {
    return [];
  }

  const toolDerivedValueColumnsAnalysis = buildValueColumnsAnalysis(latestAssistantMessage);
  if (toolDerivedValueColumnsAnalysis) {
    return toolDerivedValueColumnsAnalysis;
  }

  const toolDerivedAnalysis = buildValueArrayAnalysis(latestAssistantMessage);
  if (toolDerivedAnalysis) {
    return toolDerivedAnalysis;
  }

  if (latestAssistantMessage.analysis && latestAssistantMessage.analysis.length > 0) {
    return latestAssistantMessage.analysis;
  }

  return [];
}