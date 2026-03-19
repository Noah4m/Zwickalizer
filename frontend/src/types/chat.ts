export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCall[];
  analysis?: AnalysisData[];
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
  color?: string;
}

export interface AnalysisChartData {
  kind: "bar" | "line";
  xKey: string;
  points: Array<Record<string, string | number | null>>;
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
