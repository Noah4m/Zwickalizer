import { motion } from "framer-motion";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AnalysisChartData,
  AnalysisData,
  AnalysisStat,
  AnalysisTableData,
} from "@/types/chat";

interface AnalysisVaultProps {
  data: AnalysisData[];
}

const colorMap = {
  primary: "hsl(var(--primary))",
  accent: "hsl(var(--accent))",
  muted: "hsl(var(--muted-foreground))",
};

const mutedColor = "hsl(var(--muted-foreground))";
const gridColor = "hsl(var(--border))";
const tooltipBackground = "hsl(var(--card) / 0.92)";
const tooltipBorder = "1px solid hsl(var(--border))";

function resolveSeriesColor(color: string | undefined, index: number) {
  if (color && color in colorMap) {
    return colorMap[color as keyof typeof colorMap];
  }

  if (color) {
    return color;
  }

  const fallbackPalette = [
    colorMap.primary,
    colorMap.accent,
    "#f59e0b",
    "#10b981",
    "#6366f1",
    "#ef4444",
    "#06b6d4",
    "#8b5cf6",
  ];
  return fallbackPalette[index % fallbackPalette.length];
}

function StatsSection({ title, stats }: { title: string; stats: AnalysisStat[] }) {
  return (
    <section className="space-y-3">
      <h3 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">{title}</h3>
      <div className="grid grid-cols-2 gap-3">
        {stats.map((stat) => (
          <div key={stat.label} className="rounded-[24px] border border-border/60 bg-card/70 p-4 shadow-[var(--shadow-soft)] backdrop-blur-xl">
            <p className="text-xs text-muted-foreground font-mono uppercase tracking-wider">{stat.label}</p>
            <p className="mt-1 text-xl font-mono font-semibold text-foreground">{stat.value}</p>
            {stat.delta && (
              <p
                className={`mt-1 text-xs font-mono ${
                  stat.delta.startsWith("+") ? "text-primary" : stat.delta.startsWith("-") ? "text-destructive" : "text-muted-foreground"
                }`}
              >
                {stat.delta}
              </p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function ChartSection({ title, subtitle, chart }: { title: string; subtitle?: string; chart: AnalysisChartData }) {
  const isBar = chart.kind === "bar";
  const Chart = isBar ? BarChart : LineChart;

  return (
    <section className="rounded-[28px] border border-border/60 bg-card/70 p-5 shadow-[var(--shadow-soft)] backdrop-blur-xl">
      <div className="mb-4">
        <h3 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">{title}</h3>
        {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <Chart data={chart.points}>
          <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
          <XAxis
            dataKey={chart.xKey}
            tick={{ fill: mutedColor, fontSize: 11, fontFamily: "JetBrains Mono" }}
            minTickGap={24}
          />
          <YAxis
            tick={{ fill: mutedColor, fontSize: 11, fontFamily: "JetBrains Mono" }}
            label={chart.yAxisLabel ? { value: chart.yAxisLabel, angle: -90, position: "insideLeft", fill: mutedColor, fontSize: 10 } : undefined}
          />
          <Tooltip
            contentStyle={{
              background: tooltipBackground,
              border: tooltipBorder,
              borderRadius: "16px",
              fontFamily: "JetBrains Mono",
              fontSize: "12px",
              backdropFilter: "blur(16px)",
            }}
            labelStyle={{ color: mutedColor }}
          />
          {chart.series.length > 1 && (
            <Legend
              wrapperStyle={{ fontFamily: "JetBrains Mono", fontSize: "11px", color: mutedColor, paddingTop: "10px" }}
            />
          )}
          {chart.series.map((series, index) =>
            isBar ? (
              <Bar
                key={series.key}
                dataKey={series.key}
                name={series.label}
                fill={resolveSeriesColor(series.color, index)}
                radius={[10, 10, 0, 0]}
              />
            ) : (
              <Line
                key={series.key}
                type="monotone"
                dataKey={series.key}
                name={series.label}
                stroke={resolveSeriesColor(series.color, index)}
                strokeWidth={2.5}
                connectNulls={false}
                isAnimationActive={false}
                dot={
                  chart.points.length <= 80
                    ? { fill: resolveSeriesColor(series.color, index), r: 2.5 }
                    : false
                }
              />
            ),
          )}
        </Chart>
      </ResponsiveContainer>
    </section>
  );
}

function TableSection({ title, table }: { title: string; table: AnalysisTableData }) {
  return (
    <section className="overflow-hidden rounded-[28px] border border-border/60 bg-card/70 shadow-[var(--shadow-soft)] backdrop-blur-xl">
      <div className="border-b border-border/60 px-5 py-4">
        <h3 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">{title}</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/60 bg-secondary/50">
              {table.columns.map((column) => (
                <th key={column} className="px-4 py-3 text-left font-mono text-xs uppercase tracking-wider text-muted-foreground">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, index) => (
              <tr key={index} className="border-b border-border/50 last:border-b-0">
                {table.columns.map((column) => (
                  <td key={column} className="px-4 py-3 text-foreground">
                    {String(row[column] ?? "—")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function AnalysisVault({ data }: AnalysisVaultProps) {
  return (
    <motion.div
      initial={{ opacity: 0, x: 40 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      className="flex h-full flex-col gap-4 overflow-y-auto bg-transparent p-5"
    >
      <div className="mb-1 flex items-center gap-2">
        <div className="h-4 w-1 rounded-sm bg-primary" />
        <h2 className="font-mono text-sm uppercase tracking-widest text-muted-foreground">
          Analysis Vault
        </h2>
      </div>

      {data.length === 0 ? (
        <div className="flex flex-1 items-center justify-center rounded-[28px] border border-dashed border-border/60 bg-card/45 p-6 text-center text-sm text-muted-foreground backdrop-blur-xl">
          Ask a question to generate plots, statistics, and tabular outputs.
        </div>
      ) : (
        data.map((section, index) => {
          if (section.type === "stats") {
            return <StatsSection key={`${section.title}-${index}`} title={section.title} stats={section.data as AnalysisStat[]} />;
          }

          if (section.type === "chart") {
            return <ChartSection key={`${section.title}-${index}`} title={section.title} subtitle={section.subtitle} chart={section.data as AnalysisChartData} />;
          }

          return <TableSection key={`${section.title}-${index}`} title={section.title} table={section.data as AnalysisTableData} />;
        })
      )}
    </motion.div>
  );
}
