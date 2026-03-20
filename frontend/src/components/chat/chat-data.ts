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
const MAX_PLOTTED_SERIES = 8;

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

function normalizeComparisonSeries(
  points: Array<{ index: number; value: number | null }>,
): Array<{ index: number; value: number | null }> {
  const finitePoints = points.filter(
    (point): point is { index: number; value: number } =>
      point.value !== null && isFiniteNumber(point.value),
  );

  return finitePoints.map((point, index) => ({
    index,
    value: point.value,
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

function buildValueColumnsAnalysis(message: ChatMessage): AnalysisData[] | null {
  const toolCall = [...(message.toolCalls ?? [])]
    .reverse()
    .find((entry) =>
      entry.name === "db_get_test_value_columns" || entry.name === "db_compare_two_tests");

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
  const testIds = Array.isArray(result.testIds)
    ? result.testIds.filter((value): value is string => typeof value === "string" && value.trim().length > 0)
    : typeof result.testId === "string"
      ? [result.testId]
      : [];
  const comparisonMode =
    toolCall.name === "db_compare_two_tests" ||
    Boolean(result.comparisonMode) ||
    testIds.length > 1;

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
    .map((entry) => ({
      ...entry,
      points: comparisonMode ? normalizeComparisonSeries(entry.points) : entry.points,
    }))
    .filter((entry) => entry.points.length > 0);

  if (plottedColumns.length === 0) {
    return null;
  }

  const visibleColumns = plottedColumns.slice(0, MAX_PLOTTED_SERIES);
  const hiddenSeriesCount = Math.max(0, plottedColumns.length - visibleColumns.length);

  const longestSeries = Math.max(
    0,
    ...seriesSummaries.map((summary) =>
      summary && typeof summary === "object" && typeof summary.points === "number"
        ? summary.points
        : 0,
    ),
    ...visibleColumns.map((column) => column.points.length),
  );
  const points = buildChartPoints(
    visibleColumns.map((column, seriesIndex) => ({
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
    ...visibleColumns.map((column) => column.points.length),
  );

  const strict = Boolean(result.strict ?? true);
  const valuesLimit =
    typeof result.valuesLimit === "number" ? result.valuesLimit : null;
  const testId = typeof result.testId === "string" ? result.testId : "Unknown";
  const sharedUnitTableId =
    visibleColumns.length > 0 &&
    visibleColumns.every((column) => column.unitTableId === visibleColumns[0].unitTableId)
      ? visibleColumns[0].unitTableId
      : undefined;
  const summaryStats = seriesSummaries
    .map((summary) =>
      summary && typeof summary === "object" ? (summary as Record<string, unknown>) : null,
    )
    .filter((summary): summary is Record<string, unknown> => summary !== null);
  const signalNames = Array.from(
    new Set(
      summaryStats
        .map((summary) => summary.name)
        .filter((value): value is string => typeof value === "string" && value.trim().length > 0),
    ),
  );
  const signalLabel = signalNames.length === 1
    ? signalNames[0]
    : visibleColumns[0]?.label ?? "Value columns";
  const summaryMaxValues = summaryStats
    .map((summary) => summary.max)
    .filter((value): value is number => isFiniteNumber(value));
  const summaryMinValues = summaryStats
    .map((summary) => summary.min)
    .filter((value): value is number => isFiniteNumber(value));
  const sampledValues = visibleColumns
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
  const testLabel = comparisonMode
    ? testIds.join(" vs ")
    : testId;
  const chartTitle = comparisonMode ? "Compared test value columns" : "Test value columns";
  const statsTitle = comparisonMode ? "Value column comparison summary" : "Value column plot summary";
  const chartSubtitle = hiddenSeriesCount > 0
    ? `${comparisonMode ? `Comparing tests ${testLabel}` : `Test ${testLabel}`}. Showing the first ${visibleColumns.length} of ${plottedColumns.length} returned value columns to keep the chart readable. ${sampledPointCount} points per visible series were kept for plotting.`
    : sampledDown
      ? `${comparisonMode ? `Comparing tests ${testLabel}` : `Test ${testLabel}`}. ${comparisonMode ? "Each returned value column is aligned over finite sample index for direct curve comparison." : "Each returned value column is shown as a sampled line over the original sample index."} ${sampledPointCount} points per series were kept for plotting.`
      : `${comparisonMode ? `Comparing tests ${testLabel}` : `Test ${testLabel}`}. Each returned value column is shown as a separate line over sample index.`;

  return [
    {
      type: "stats",
      title: statsTitle,
      data: [
        { label: "Signal", value: signalLabel, delta: "connected" },
        { label: "Points", value: String(longestSeries), delta: "total samples" },
        { label: "Max", value: maxVal !== null ? formatValue(maxVal) : "—", delta: "breakpoint" },
        { label: "Min", value: minVal !== null ? formatValue(minVal) : "—", delta: "lowest recorded" },
      ],
    },
    {
      type: "chart",
      title: chartTitle,
      subtitle: chartSubtitle,
      data: {
        kind: "line",
        xKey: "index",
        yAxisLabel: sharedUnitTableId ?? "Value",
        points,
        series: visibleColumns.map((column, seriesIndex) => ({
          key: `series_${seriesIndex + 1}`,
          label: column.label,
        })),
      },
    },
  ];
}

function buildFindTestsAnalysis(message: ChatMessage): AnalysisData[] | null {
  const toolCall = [...(message.toolCalls ?? [])]
    .reverse()
    .find((entry) => entry.name === "db_find_tests");

  if (!toolCall || typeof toolCall.result !== "object" || toolCall.result === null) {
    return null;
  }

  const result = toolCall.result as Record<string, unknown>;
  const tests = result.tests;
  if (!Array.isArray(tests) || tests.length === 0) {
    return null;
  }

  // Fixed fields that always appear first if present
  const fixedFirst = ["name", "testId", "date"];
  // Fields to exclude from the metadata table
  const excluded = new Set(["availableColumns"]);

  // Collect all keys across all tests dynamically
  const allKeys = new Set<string>();
  tests.forEach((test) => {
    Object.keys(test as Record<string, unknown>).forEach((k) => allKeys.add(k));
  });

  // Build ordered column list: fixed first, then the rest alphabetically
  const metaColumns = [
    ...fixedFirst.filter((k) => allKeys.has(k)),
    ...[...allKeys]
      .filter((k) => !fixedFirst.includes(k) && !excluded.has(k))
      .sort(),
  ];

  // Only keep columns that have at least one non-null value
  const activeMetaColumns = metaColumns.filter((col) =>
    tests.some((test) => {
      const val = (test as Record<string, unknown>)[col];
      if (val === null || val === undefined || val === "") return false;
      const str = String(val);
      return str !== "—" && str !== "[object Object]";
    }),
  );

  const metaRows = tests.map((test) => {
    const t = test as Record<string, unknown>;
    const row: Record<string, string> = {};
    activeMetaColumns.forEach((col) => {
      const val = t[col];
      row[col] = val !== null && val !== undefined ? String(val) : "—";
    });
    return row;
  });

  // Available columns as separate table with badges
  const columnRows = tests.map((test) => {
    const t = test as Record<string, unknown>;
    const cols = Array.isArray(t.availableColumns)
      ? [...new Set(t.availableColumns as string[])].filter(Boolean)
      : [];
    return {
      name: typeof t.name === "string" && t.name
        ? t.name
        : typeof t.testId === "string"
        ? t.testId
        : "—",
      availableColumns: cols.join(" | "),
    };
  });

  return [
    {
      type: "table",
      title: "Test metadata",
      data: {
        columns: activeMetaColumns,
        rows: metaRows,
      },
    },
    {
      type: "table",
      title: "Available columns",
      data: {
        columns: ["name", "availableColumns"],
        rows: columnRows,
      },
    },
  ];
}

export function deriveAnalysisData(messages: ChatMessage[]): AnalysisData[] {
  const latestAssistantMessage = [...messages].reverse().find((message) => message.role === "assistant");

  if (!latestAssistantMessage) {
    return [];
  }

  const findTestsAnalysis = buildFindTestsAnalysis(latestAssistantMessage);
  if (findTestsAnalysis) {
    return findTestsAnalysis;
  }

  const toolDerivedValueColumnsAnalysis = buildValueColumnsAnalysis(latestAssistantMessage);
  if (toolDerivedValueColumnsAnalysis) {
    return toolDerivedValueColumnsAnalysis;
  }

  if (latestAssistantMessage.analysis && latestAssistantMessage.analysis.length > 0) {
    return latestAssistantMessage.analysis;
  }

  return [];
}
