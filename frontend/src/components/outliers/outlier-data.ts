export type OutlierSeverity = "high" | "medium" | "low";

export interface OutlierMetric {
  label: string;
  value: string;
  note?: string;
}

export interface OutlierRecord {
  id: string;
  severity: OutlierSeverity;
  title: string;
  summary: string;
  testId: string;
  material: string;
  customer: string;
  tester: string;
  machine: string;
  recordedAt: string;
  reason: string;
  setupNotes: string[];
  signals: string[];
  recommendedActions: string[];
  metrics: OutlierMetric[];
}

export const sampleOutliers: OutlierRecord[] = [
  {
    id: "OUT-104",
    severity: "high",
    title: "Force curve spike during tensile run",
    summary:
      "The measured force jumps sharply in the first third of the run and then returns to the expected profile.",
    testId: "T-2026-1048",
    material: "PA12 GF30",
    customer: "Company_3",
    tester: "M. Keller",
    machine: "Zwick Z250 / Line 2",
    recordedAt: "2026-03-17 14:42",
    reason:
      "Detected as an outlier because the peak force exceeds the local batch median by 31% while strain values stay in-range.",
    setupNotes: [
      "Specimen width entered as 12.5 mm.",
      "Humidity chamber was enabled for this batch.",
      "Grip replacement was logged on the same machine earlier that day.",
    ],
    signals: [
      "Force maximum much higher than neighboring tests.",
      "Curve shape suggests transient clamp slip or wrong zeroing.",
      "Single-test issue; adjacent runs look stable.",
    ],
    recommendedActions: [
      "Contact tester to confirm clamp setup and zeroing.",
      "Flag for manual re-check before using in downstream analytics.",
      "Keep raw data for audit trail even if excluded later.",
    ],
    metrics: [
      { label: "Batch deviation", value: "+31%", note: "vs median max force" },
      { label: "Curve anomaly score", value: "0.92", note: "high confidence" },
      { label: "Neighbor agreement", value: "1 / 6", note: "only one similar run" },
      { label: "Spec status", value: "Unclear", note: "force high, strain normal" },
    ],
  },
  {
    id: "OUT-105",
    severity: "medium",
    title: "Suspicious machine setup for charpy impact test",
    summary:
      "The pendulum energy and operator comments do not match the expected setup for the selected test recipe.",
    testId: "T-2026-1055",
    material: "ABS V0",
    customer: "Company_7",
    tester: "L. Braun",
    machine: "Charpy Rig / Bay 1",
    recordedAt: "2026-03-16 09:18",
    reason:
      "Recipe metadata implies 15 J setup, but the run was stored with a 7.5 J machine configuration and unusually low absorbed energy.",
    setupNotes: [
      "Operator note mentions quick recipe switch before the run.",
      "Machine calibration is current.",
      "No duplicate records found for this specimen.",
    ],
    signals: [
      "Setup metadata conflict between recipe and machine state.",
      "Absorbed energy low but still physically plausible.",
      "Could be a valid edge case or a configuration mistake.",
    ],
    recommendedActions: [
      "Ask tester whether the recipe switch was intentional.",
      "Compare with lab notebook or raw machine export.",
      "Leave in database but mark as reviewed if justified.",
    ],
    metrics: [
      { label: "Recipe mismatch", value: "15 J vs 7.5 J", note: "stored configuration" },
      { label: "Absorbed energy", value: "3.1 J", note: "lower than batch norm" },
      { label: "Batch percentile", value: "4th", note: "rare but not impossible" },
      { label: "Confidence", value: "0.71", note: "medium confidence" },
    ],
  },
  {
    id: "OUT-106",
    severity: "low",
    title: "Diameter entry likely rounded incorrectly",
    summary:
      "Mechanical results are in-family, but the specimen geometry looks copied from a neighboring sample instead of measured individually.",
    testId: "T-2026-1061",
    material: "AlSi10Mg",
    customer: "Company_2",
    tester: "A. Meier",
    machine: "Zwick Z010 / Line 4",
    recordedAt: "2026-03-14 11:05",
    reason:
      "Outlier rule flagged the specimen diameter because five consecutive tests use the exact same geometry value with more precision than usual.",
    setupNotes: [
      "Run outcome itself is stable.",
      "Same tester entered the whole batch.",
      "Possible copy-forward data entry pattern.",
    ],
    signals: [
      "Metadata issue rather than measurement failure.",
      "Low impact on trend analysis if mechanical values remain consistent.",
      "Worth reviewing if geometry is used for recalculation later.",
    ],
    recommendedActions: [
      "Leave in database but add note if geometry is confirmed approximate.",
      "Contact tester only if geometry precision matters for the report.",
      "Exclude from geometry-sensitive dashboards if unresolved.",
    ],
    metrics: [
      { label: "Repeated geometry value", value: "5 runs", note: "identical to 0.001 mm" },
      { label: "Mechanical drift", value: "+2%", note: "within normal spread" },
      { label: "Data risk", value: "Low", note: "mainly metadata quality" },
      { label: "Confidence", value: "0.46", note: "review suggested" },
    ],
  },
];
