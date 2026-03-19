import { describe, expect, it } from "vitest";

import { deriveAnalysisData } from "@/components/chat/chat-data";
import type { ChatMessage } from "@/types/chat";

describe("deriveAnalysisData", () => {
  it("builds a deterministic line plot from db_get_test_value_columns tool results", () => {
    const messages: ChatMessage[] = [
      {
        role: "user",
        content: "plot the value columns",
      },
      {
        role: "assistant",
        content: "I plotted the returned value columns.",
        toolCalls: [
          {
            name: "db_get_test_value_columns",
            args: { test_id: "T-700", include_values: true },
            result: {
              testId: "T-700",
              strict: true,
              includeValues: true,
              valuesLimit: null,
              seriesSummaries: [
                { label: "Force", points: 3, sampledPoints: 3, sampledDown: false },
                { label: "Strain", points: 3, sampledPoints: 3, sampledDown: false },
              ],
              valueColumns: [
                {
                  name: "Force",
                  sampledIndices: [0, 1, 2],
                  sampledValues: [1, 2, 3],
                },
                {
                  name: "Strain",
                  sampledIndices: [0, 1, 2],
                  sampledValues: [4, 5, 6],
                },
              ],
            },
          },
        ],
      },
    ];

    const analysis = deriveAnalysisData(messages);

    expect(analysis).toHaveLength(2);
    expect(analysis[0].type).toBe("stats");
    expect(analysis[1].type).toBe("chart");

    const chart = analysis[1].data;
    expect("kind" in chart && chart.kind).toBe("line");
    expect("series" in chart && chart.series).toEqual([
      { key: "series_1", label: "Force" },
      { key: "series_2", label: "Strain" },
    ]);
    expect("points" in chart && chart.points).toEqual([
      { index: 0, series_1: 1, series_2: 4 },
      { index: 1, series_1: 2, series_2: 5 },
      { index: 2, series_1: 3, series_2: 6 },
    ]);
  });

  it("builds a deterministic line plot from db_get_test_value_arrays tool results", () => {
    const messages: ChatMessage[] = [
      {
        role: "user",
        content: "plot the first value column",
      },
      {
        role: "assistant",
        content: "I plotted the returned values.",
        toolCalls: [
          {
            name: "db_get_test_value_arrays",
            args: { test_id: "T-500", value_column_index: 0 },
            result: {
              testId: "T-500",
              strict: true,
              valuesLimit: null,
              seriesSummaries: [{ label: "Result 1", min: 1, max: 3, points: 3, sampledPoints: 3, sampledDown: false }],
              valueArrays: [
                {
                  label: "Result 1",
                  sampledIndices: [0, 1, 2],
                  sampledValues: [1, 2, 3],
                },
              ],
            },
          },
        ],
      },
    ];

    const analysis = deriveAnalysisData(messages);

    expect(analysis).toHaveLength(2);
    expect(analysis[0].type).toBe("stats");
    expect(analysis[1].type).toBe("chart");

    const chart = analysis[1].data;
    expect("kind" in chart && chart.kind).toBe("line");
    expect("series" in chart && chart.series).toHaveLength(1);
    expect("points" in chart && chart.points).toEqual([
      { index: 0, series_1: 1 },
      { index: 1, series_1: 2 },
      { index: 2, series_1: 3 },
    ]);
  });
});
