import { useMemo, useState } from "react";
import { AlertTriangle, ArrowRight, CheckCircle2, Mail, ShieldAlert, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  sampleOutliers,
  type OutlierRecord,
} from "@/components/outliers/outlier-data";

type ReviewAction = "remove" | "contact" | "keep" | "recheck";

interface ResolvedOutlier {
  outlierId: string;
  title: string;
  action: ReviewAction;
}

const actionLabels: Record<ReviewAction, string> = {
  remove: "Removed from active dataset",
  contact: "Tester follow-up requested",
  keep: "Kept in database",
  recheck: "Marked for re-check",
};

export default function OutlierWorkbench() {
  const [pendingOutliers, setPendingOutliers] = useState<OutlierRecord[]>(sampleOutliers);
  const [selectedId, setSelectedId] = useState<string>(sampleOutliers[0]?.id ?? "");
  const [resolved, setResolved] = useState<ResolvedOutlier[]>([]);

  const selectedOutlier = useMemo(
    () => pendingOutliers.find((outlier) => outlier.id === selectedId) ?? pendingOutliers[0] ?? null,
    [pendingOutliers, selectedId],
  );

  const resolveOutlier = (action: ReviewAction) => {
    if (!selectedOutlier) return;

    const nextPending = pendingOutliers.filter((item) => item.id !== selectedOutlier.id);
    setPendingOutliers(nextPending);
    setResolved((current) => [
      {
        outlierId: selectedOutlier.id,
        title: selectedOutlier.title,
        action,
      },
      ...current,
    ]);
    setSelectedId(nextPending[0]?.id ?? "");
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 p-4 md:p-6">
      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-[28px] border border-border/60 bg-card/70 p-5 shadow-[var(--shadow-soft)] backdrop-blur-xl">
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted-foreground">Pending</p>
          <p className="mt-2 font-mono text-3xl text-foreground">{pendingOutliers.length}</p>
        </div>
        <div className="rounded-[28px] border border-border/60 bg-card/70 p-5 shadow-[var(--shadow-soft)] backdrop-blur-xl">
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted-foreground">Current test</p>
          <p className="mt-2 font-mono text-3xl text-foreground">{selectedOutlier?.testId ?? "--"}</p>
        </div>
        <div className="rounded-[28px] border border-border/60 bg-card/70 p-5 shadow-[var(--shadow-soft)] backdrop-blur-xl">
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted-foreground">Reviewed</p>
          <p className="mt-2 font-mono text-3xl text-foreground">{resolved.length}</p>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[320px_minmax(0,1fr)_320px]">
        <aside className="min-h-0 overflow-hidden rounded-[32px] border border-border/60 bg-card/55 shadow-[var(--shadow-soft)] backdrop-blur-xl">
          <div className="border-b border-border/60 px-5 py-4">
            <p className="font-mono text-xs uppercase tracking-[0.22em] text-muted-foreground">Queue</p>
          </div>
          <div className="max-h-full space-y-3 overflow-y-auto p-4">
            {pendingOutliers.length === 0 ? (
              <div className="rounded-[24px] border border-dashed border-border/60 bg-background/40 p-4 text-sm text-muted-foreground">
                No pending outliers.
              </div>
            ) : (
              pendingOutliers.map((outlier) => {
                const isActive = outlier.id === selectedOutlier?.id;

                return (
                  <button
                    key={outlier.id}
                    onClick={() => setSelectedId(outlier.id)}
                    className={cn(
                      "w-full rounded-[24px] border p-4 text-left transition-all",
                      isActive
                        ? "border-primary/40 bg-primary/10 shadow-[var(--shadow-soft)]"
                        : "border-border/60 bg-background/55 hover:border-primary/30 hover:bg-background/70",
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-mono text-xs uppercase tracking-[0.18em] text-foreground">{outlier.id}</p>
                        <p className="mt-2 text-sm font-medium text-foreground">{outlier.title}</p>
                      </div>
                    </div>
                    <p className="mt-2 text-xs uppercase tracking-[0.16em] text-muted-foreground">
                      {outlier.testId} - {outlier.machine}
                    </p>
                    <p className="mt-3 text-sm text-muted-foreground">{outlier.summary}</p>
                  </button>
                );
              })
            )}
          </div>
        </aside>

        <section className="min-h-0 overflow-y-auto rounded-[32px] border border-border/60 bg-card/65 shadow-[var(--shadow-elevated)] backdrop-blur-2xl">
          {selectedOutlier ? (
            <div className="space-y-6 p-5 md:p-6">
              <div className="flex flex-col gap-4 border-b border-border/60 pb-5 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-xs uppercase tracking-[0.18em] text-muted-foreground">
                      {selectedOutlier.testId}
                    </span>
                    <span className="font-mono text-xs uppercase tracking-[0.18em] text-muted-foreground">
                      {selectedOutlier.material}
                    </span>
                  </div>
                  <h2 className="mt-4 text-2xl text-foreground">{selectedOutlier.title}</h2>
                </div>
                <div className="rounded-[24px] border border-border/60 bg-background/45 p-4 text-sm text-muted-foreground">
                  <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Recorded</p>
                  <p className="mt-2 text-foreground">{selectedOutlier.recordedAt}</p>
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                {selectedOutlier.metrics.map((metric) => (
                  <div key={metric.label} className="rounded-[24px] border border-border/60 bg-background/45 p-4">
                    <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{metric.label}</p>
                    <p className="mt-2 font-mono text-xl text-foreground">{metric.value}</p>
                    {metric.note && <p className="mt-1 text-xs text-muted-foreground">{metric.note}</p>}
                  </div>
                ))}
              </div>

              <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
                <div className="rounded-[28px] border border-border/60 bg-background/45 p-5">
                  <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">Flag</p>
                  <p className="mt-3 text-sm leading-relaxed text-foreground">{selectedOutlier.reason}</p>
                </div>
                <div className="rounded-[28px] border border-border/60 bg-background/45 p-5">
                  <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">Context</p>
                  <div className="mt-3 space-y-2 text-sm text-foreground">
                    <p><span className="text-muted-foreground">Material:</span> {selectedOutlier.material}</p>
                    <p><span className="text-muted-foreground">Customer:</span> {selectedOutlier.customer}</p>
                    <p><span className="text-muted-foreground">Tester:</span> {selectedOutlier.tester}</p>
                    <p><span className="text-muted-foreground">Machine:</span> {selectedOutlier.machine}</p>
                  </div>
                </div>
              </div>

              <div className="grid gap-4 xl:grid-cols-2">
                <div className="rounded-[28px] border border-border/60 bg-background/45 p-5">
                  <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">Signals</p>
                  <div className="mt-4 space-y-3">
                    {selectedOutlier.signals.map((signal) => (
                      <div key={signal} className="flex items-start gap-3 rounded-[20px] border border-border/50 bg-card/60 px-4 py-3">
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                        <p className="text-sm text-foreground">{signal}</p>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="rounded-[28px] border border-border/60 bg-background/45 p-5">
                  <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">Setup</p>
                  <div className="mt-4 space-y-3">
                    {selectedOutlier.setupNotes.map((note) => (
                      <div key={note} className="rounded-[20px] border border-border/50 bg-card/60 px-4 py-3 text-sm text-foreground">
                        {note}
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="rounded-[28px] border border-border/60 bg-background/45 p-5">
                <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">Suggested actions</p>
                <div className="mt-4 grid gap-3 md:grid-cols-3">
                  {selectedOutlier.recommendedActions.map((item) => (
                    <div key={item} className="rounded-[20px] border border-border/50 bg-card/60 px-4 py-4 text-sm text-foreground">
                      {item}
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-[30px] border border-primary/25 bg-primary/10 p-5">
                <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                  <div>
                    <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">Decision</p>
                  </div>
                  <ArrowRight className="hidden h-5 w-5 text-primary md:block" />
                </div>
                <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                  <Button className="h-auto justify-start rounded-[22px] px-4 py-4" onClick={() => resolveOutlier("remove")}>
                    <Trash2 className="mr-2 h-4 w-4" />
                    Remove
                  </Button>
                  <Button variant="outline" className="h-auto justify-start rounded-[22px] px-4 py-4" onClick={() => resolveOutlier("contact")}>
                    <Mail className="mr-2 h-4 w-4" />
                    Contact tester
                  </Button>
                  <Button variant="outline" className="h-auto justify-start rounded-[22px] px-4 py-4" onClick={() => resolveOutlier("keep")}>
                    <CheckCircle2 className="mr-2 h-4 w-4" />
                    Leave in DB
                  </Button>
                  <Button variant="outline" className="h-auto justify-start rounded-[22px] px-4 py-4" onClick={() => resolveOutlier("recheck")}>
                    <ShieldAlert className="mr-2 h-4 w-4" />
                    Re-check later
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center p-8 text-center">
              <div className="max-w-md rounded-[32px] border border-dashed border-border/60 bg-background/45 p-8">
                <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">Queue complete</p>
                <h2 className="mt-3 text-2xl text-foreground">No outliers left</h2>
              </div>
            </div>
          )}
        </section>

        <aside className="min-h-0 overflow-hidden rounded-[32px] border border-border/60 bg-card/55 shadow-[var(--shadow-soft)] backdrop-blur-xl">
          <div className="border-b border-border/60 px-5 py-4">
            <p className="font-mono text-xs uppercase tracking-[0.22em] text-muted-foreground">Session log</p>
          </div>
          <div className="max-h-full space-y-3 overflow-y-auto p-4">
            {resolved.length === 0 ? (
              <div className="rounded-[24px] border border-dashed border-border/60 bg-background/40 p-4 text-sm text-muted-foreground">
                No actions yet.
              </div>
            ) : (
              resolved.map((entry) => (
                <div key={`${entry.outlierId}-${entry.action}`} className="rounded-[24px] border border-border/60 bg-background/55 p-4">
                  <p className="font-mono text-xs uppercase tracking-[0.18em] text-muted-foreground">{entry.outlierId}</p>
                  <p className="mt-2 text-sm font-medium text-foreground">{entry.title}</p>
                  <p className="mt-2 text-sm text-muted-foreground">{actionLabels[entry.action]}</p>
                </div>
              ))
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
