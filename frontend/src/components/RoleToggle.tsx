export type UserRole = "engineer" | "executive";

export default function RoleToggle() {
  return (
    <div className="flex items-center rounded-full border border-primary/70 bg-primary px-4 py-2 text-[11px] font-mono tracking-[0.18em] text-primary-foreground shadow-[var(--shadow-soft)] backdrop-blur-xl">
      Role: engineer
    </div>
  );
}
