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

function normalizeSampledSeries(
  sampledIndices: unknown,
  sampledValues: unknown,
): Array<{ index: number; value: number | null }> {
  const indexes = Array.isArray(sampledIndices)
    ? sampledIndices.filter((value): value is number => Number.isInteger(value) && value >= 0)
    : [];
  const values = Array.isArray(sampledValues)
    ? sampledValues.map((value) => (isFiniteNumber(value) ? value : null))
    : [];
  const pairCount = Math.min(indexes.length, values.length);

  return Array.from({ length: pairCount }, (_, index) => ({
    index: indexes[index],
    value: values[index],
  }));
}

function buildChartPoints(
  series: Array<{ key: string; points: Array<{ index: number; value: number | null }> }>,
) {
  const allIndexes = Array.from(
    new Set(series.flatMap((entry) => entry.points.map((point) => point.index))),
  ).sort((left, right) => left - right);

  return allIndexes.map((index) => {
    const point: Record<string, string | number | null> = { index };
    series.forEach((entry) => {
      point[entry.key] =
        entry.points.find((item) => item.index === index)?.value ?? null;
    });
    return point;
  });
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
  const plottedSeries = rawValueArrays.map((entry, seriesIndex) => {
    const key = `series_${seriesIndex + 1}`;
    const summary = seriesSummaries[seriesIndex];
    const fallbackLabel =
      summary && typeof summary === "object" && typeof summary.label === "string"
        ? summary.label
        : `Result ${seriesIndex + 1}`;

    if (typeof entry === "object" && entry !== null && !Array.isArray(entry)) {
      const record = entry as Record<string, unknown>;
      return {
        key,
        label: typeof record.label === "string" ? record.label : fallbackLabel,
        points: normalizeSampledSeries(record.sampledIndices, record.sampledValues),
      };
    }

    const values = Array.isArray(entry)
      ? entry.map((value) => (isFiniteNumber(value) ? value : null))
      : [];
    const indexes = sampleIndexes(values.length);
    return {
      key,
      label: fallbackLabel,
      points: indexes.map((index) => ({ index, value: values[index] ?? null })),
    };
  });
  const points = buildChartPoints(plottedSeries);
  const longestSeries = Math.max(
    0,
    ...seriesSummaries.map((summary) =>
      summary && typeof summary === "object" && typeof summary.points === "number"
        ? summary.points
        : 0,
    ),
    ...plottedSeries.map((series) => series.points.length),
  );
  const sampledDown = seriesSummaries.some(
    (summary) =>
      Boolean(
        summary &&
          typeof summary === "object" &&
          "sampledDown" in summary &&
          (summary as Record<string, unknown>).sampledDown,
      ),
  );
  const sampledPointCount = Math.max(
    0,
    ...seriesSummaries.map((summary) =>
      summary && typeof summary === "object" && typeof summary.sampledPoints === "number"
        ? summary.sampledPoints
        : 0,
    ),
    ...plottedSeries.map((series) => series.points.length),
  );
  const strict = Boolean(result.strict ?? true);
  const valuesLimit =
    typeof result.valuesLimit === "number" ? result.valuesLimit : null;
  const testId = typeof result.testId === "string" ? result.testId : "Unknown";

  return [
    {
      type: "stats",
      title: "Value array plot summary",
      data: [
        { label: "Series", value: String(plottedSeries.length), delta: "plotted" },
        { label: "Longest line", value: String(longestSeries), delta: "points" },
        { label: "Mode", value: strict ? "Strict" : "Loose", delta: "matching" },
        {
          label: "Limit",
          value: valuesLimit === null ? "Full" : String(valuesLimit),
          delta: valuesLimit === null ? "returned" : "per line",
        },
      ],
    },
    {
      type: "chart",
      title: "Test value arrays",
      subtitle:
        sampledDown
          ? `Test ${testId}. Each returned value array is shown as a sampled line over the original sample index. ${sampledPointCount} points per series were kept for plotting.`
          : `Test ${testId}. Each returned value array is shown as a separate line over sample index.`,
      data: {
        kind: "line",
        xKey: "index",
        yAxisLabel: "Value",
        points,
        series: plottedSeries.map((series) => ({
          key: series.key,
          label: series.label,
        })),
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
    .map((entry) => (typeof entry === "object" && entry !== null ? (entry as Record<string, unknown>) : null))
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
        points:
          Array.isArray(entry.sampledIndices) && Array.isArray(entry.sampledValues)
            ? normalizeSampledSeries(entry.sampledIndices, entry.sampledValues)
            : Array.isArray(entry.values)
              ? sampleIndexes(entry.values.length).map((sampleIndex) => ({
                  index: sampleIndex,
                  value: isFiniteNumber(entry.values[sampleIndex])
                    ? (entry.values[sampleIndex] as number)
                    : null,
                }))
              : [],
        unitTableId: typeof entry.unitTableId === "string" ? entry.unitTableId : undefined,
      };
    })
    .filter((entry) => entry.points.length > 0);

  if (plottedColumns.length === 0) {
    return null;
  }

  const longestSeries = Math.max(
    0,
    ...seriesSummaries.map((summary) =>
      summary && typeof summary === "object" && typeof summary.points === "number"
        ? summary.points
        : 0,
    ),
    ...plottedColumns.map((column) => column.points.length),
  );
  const points = buildChartPoints(
    plottedColumns.map((column, seriesIndex) => ({
      key: `series_${seriesIndex + 1}`,
      points: column.points,
    })),
  );
  const sampledDown = seriesSummaries.some(
    (summary) =>
      Boolean(
        summary &&
          typeof summary === "object" &&
          "sampledDown" in summary &&
          (summary as Record<string, unknown>).sampledDown,
      ),
  );
  const sampledPointCount = Math.max(
    0,
    ...seriesSummaries.map((summary) =>
      summary && typeof summary === "object" && typeof summary.sampledPoints === "number"
        ? summary.sampledPoints
        : 0,
    ),
    ...plottedColumns.map((column) => column.points.length),
  );

  const strict = Boolean(result.strict ?? true);
  const valuesLimit =
    typeof result.valuesLimit === "number" ? result.valuesLimit : null;
  const testId = typeof result.testId === "string" ? result.testId : "Unknown";
  const sharedUnitTableId =
    plottedColumns.length > 0 &&
    plottedColumns.every((column) => column.unitTableId === plottedColumns[0].unitTableId)
      ? plottedColumns[0].unitTableId
      : undefined;
  const signalLabel = plottedColumns[0]?.label ?? "Value columns";
  const summaryStats = seriesSummaries
    .map((summary) =>
      summary && typeof summary === "object" ? (summary as Record<string, unknown>) : null,
    )
    .filter((summary): summary is Record<string, unknown> => summary !== null);
  const summaryMaxValues = summaryStats
    .map((summary) => summary.max)
    .filter((value): value is number => isFiniteNumber(value));
  const summaryMinValues = summaryStats
    .map((summary) => summary.min)
    .filter((value): value is number => isFiniteNumber(value));
  const sampledValues = plottedColumns
    .flatMap((column) => column.points.map((point) => point.value))
    .filter((value): value is number => value !== null && isFiniteNumber(value));
  const maxVal = summaryMaxValues.length > 0
    ? Math.max(...summaryMaxValues)
    : sampledValues.length > 0
      ? Math.max(...sampledValues)
      : null;
  const minVal = summaryMinValues.length > 0
    ? Math.min(...summaryMinValues)
    : sampledValues.length > 0
      ? Math.min(...sampledValues)
      : null;

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
        sampledDown
          ? `Test ${testId}. Each returned value column is shown as a sampled line over the original sample index. ${sampledPointCount} points per series were kept for plotting.`
          : `Test ${testId}. Each returned value column is shown as a separate line over sample index.`,
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
  const latestAssistantMessage = [...messages].reverse().find((message) => message.role === "assistant");

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
