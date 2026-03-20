interface BrandMarkProps {
  compact?: boolean;
}

export default function BrandMark({ compact = false }: BrandMarkProps) {
  return (
    <div className="select-none">
      <h1
        className={
          compact
            ? "font-mono text-xl font-light tracking-[0.18em] text-foreground/80"
            : "mb-3 font-mono text-4xl font-light tracking-[0.18em] text-foreground/80"
        }
      >
        MAT//AI
      </h1>
      {!compact ? (
        <p className="font-mono text-xs uppercase tracking-[0.24em] text-muted-foreground">
          ask about your test data
        </p>
      ) : null}
    </div>
  );
}
