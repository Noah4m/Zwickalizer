export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCall[];
  timestamp?: Date;
}

export interface ToolCall {
  name: string;
  args: Record<string, unknown>;
  result?: unknown;
}

export interface AnalysisStat {
  label: string;
  value: string;
  delta?: string;
}

export interface AnalysisSeries {
  key: string;
  label: string;
  color?: "primary" | "accent" | "muted";
}

export interface AnalysisChartData {
  kind: "bar" | "line";
  xKey: string;
  points: Array<Record<string, string | number>>;
  series: AnalysisSeries[];
  yAxisLabel?: string;
}

export interface AnalysisTableData {
  columns: string[];
  rows: Array<Record<string, string | number>>;
}

export interface AnalysisData {
  type: "chart" | "stats" | "table";
  title: string;
  data: AnalysisStat[] | AnalysisChartData | AnalysisTableData;
  subtitle?: string;
}