import { AnalysisData, ChatMessage } from "@/types/chat";
import type { UserRole } from "@/components/RoleToggle";

export interface ChatThread {
  id: string;
  title: string;
  role: UserRole;
  messages: ChatMessage[];
  updatedAt: number;
}

const simulatedResponses: Record<string, { content: string; toolCalls?: { name: string; args: Record<string, unknown> }[] }> = {
  default: {
    content:
      "Based on the available test data, I can provide analysis across multiple material properties including tensile strength, elongation, hardness, and fatigue resistance. Please specify a test ID or material to get detailed results.",
    toolCalls: [{ name: "query_database", args: { table: "materials", limit: 10 } }],
  },
};

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

export function getSimulatedResponse(input: string, role: UserRole) {
  const lower = input.toLowerCase();

  if (lower.includes("test 3") || lower.includes("summary")) {
    return {
      content:
        role === "engineer"
          ? "**Test 3 Summary — Alloy 7075-T6**\n\nUltimate Tensile Strength: 482 MPa (within spec ±5 MPa)\nYield Strength: 331 MPa\nElongation at Break: 18.4%\nHardness: 32.6 HRC\n\nAll values within tolerance. No anomalies detected in the stress-strain curve. Specimen geometry conformed to ASTM E8 standard."
          : "**Test 3 — Executive Summary**\n\nMaterial: Alloy 7075-T6 — All metrics PASS specification requirements.\n\nKey takeaway: Material performance is consistent with supplier claims. No quality concerns flagged. Recommend continued use in production.",
      toolCalls: [
        { name: "query_test_results", args: { test_id: 3 } },
        { name: "check_specifications", args: { material: "7075-T6" } },
      ],
    };
  }

  if (lower.includes("degradation") || lower.includes("tensile")) {
    return {
      content:
        role === "engineer"
          ? "**Degradation Analysis — Material 3 (Ti-6Al-4V)**\n\nFatigue testing shows a 35% reduction in tensile strength after 100k cycles at R=0.1 loading ratio.\n\nCritical inflection point observed at ~25k cycles where degradation rate increases from 0.12%/kcycle to 0.28%/kcycle.\n\nMicrostructural analysis suggests grain boundary weakening as the primary mechanism."
          : "**Degradation Report — Material 3**\n\nYes, significant degradation detected. Tensile strength drops 35% over the full fatigue life.\n\nBusiness impact: Components using this material should be inspected or replaced at 25,000 cycle intervals to maintain safety margins.",
      toolCalls: [
        { name: "query_fatigue_data", args: { material_id: 3 } },
        { name: "compute_degradation_rate", args: { method: "piecewise_linear" } },
      ],
    };
  }

  return simulatedResponses.default;
}

export function deriveAnalysisData(messages: ChatMessage[]): AnalysisData[] {
  const lastUserMessage = [...messages].reverse().find((message) => message.role === "user")?.content.toLowerCase() ?? "";
  const lastAssistantMessage = [...messages].reverse().find((message) => message.role === "assistant")?.content.toLowerCase() ?? "";
  const signal = `${lastUserMessage} ${lastAssistantMessage}`;

  if (!lastAssistantMessage) {
    return [];
  }

  if (signal.includes("test 3") || signal.includes("7075")) {
    return [
      {
        type: "stats",
        title: "Test 3 snapshot",
        data: [
          { label: "UTS", value: "482 MPa", delta: "+2.1%" },
          { label: "Yield", value: "331 MPa", delta: "+1.4%" },
          { label: "Elongation", value: "18.4%", delta: "-0.3%" },
          { label: "Hardness", value: "32.6 HRC", delta: "+0.8%" },
        ],
      },
      {
        type: "chart",
        title: "Strength by sample",
        subtitle: "Regenerated from the selected conversation context.",
        data: {
          kind: "bar",
          xKey: "sample",
          yAxisLabel: "MPa",
          series: [
            { key: "tensile", label: "Tensile", color: "primary" },
            { key: "yield", label: "Yield", color: "accent" },
          ],
          points: [
            { sample: "S1", tensile: 478, yield: 320 },
            { sample: "S2", tensile: 485, yield: 330 },
            { sample: "S3", tensile: 472, yield: 315 },
            { sample: "S4", tensile: 490, yield: 335 },
            { sample: "S5", tensile: 488, yield: 328 },
            { sample: "S6", tensile: 465, yield: 310 },
          ],
        },
      },
      {
        type: "table",
        title: "Spec checkpoints",
        data: {
          columns: ["Metric", "Measured", "Spec", "Status"],
          rows: [
            { Metric: "UTS", Measured: "482 MPa", Spec: "480 ±5 MPa", Status: "PASS" },
            { Metric: "Yield", Measured: "331 MPa", Spec: ">= 325 MPa", Status: "PASS" },
            { Metric: "Elongation", Measured: "18.4%", Spec: ">= 17%", Status: "PASS" },
          ],
        },
      },
    ];
  }

  if (signal.includes("degradation") || signal.includes("fatigue") || signal.includes("tensile strength")) {
    return [
      {
        type: "stats",
        title: "Degradation summary",
        data: [
          { label: "Strength loss", value: "35%", delta: "-35.0%" },
          { label: "Inflection", value: "25k cycles", delta: "critical" },
          { label: "Inspection", value: "Every 25k", delta: "recommended" },
          { label: "Mechanism", value: "Grain boundary", delta: "observed" },
        ],
      },
      {
        type: "chart",
        title: "Fatigue degradation curve",
        subtitle: "Regenerated from the selected conversation context.",
        data: {
          kind: "line",
          xKey: "cycle",
          yAxisLabel: "Strength %",
          series: [{ key: "strength", label: "Remaining strength", color: "primary" }],
          points: [
            { cycle: "0", strength: 100 },
            { cycle: "1k", strength: 98 },
            { cycle: "5k", strength: 94 },
            { cycle: "10k", strength: 89 },
            { cycle: "25k", strength: 82 },
            { cycle: "50k", strength: 74 },
            { cycle: "100k", strength: 65 },
          ],
        },
      },
    ];
  }

  return [
    {
      type: "stats",
      title: "Overview",
      data: [
        { label: "Results", value: "10 rows", delta: "loaded" },
        { label: "Properties", value: "4 metrics", delta: "available" },
        { label: "Coverage", value: "3 materials", delta: "ready" },
        { label: "Mode", value: "Live query", delta: "simulated" },
      ],
    },
  ];
}
