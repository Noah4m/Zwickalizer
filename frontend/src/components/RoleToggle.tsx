export type UserRole = "engineer" | "executive";

interface RoleToggleProps {
  role: UserRole;
  onRoleChange: (role: UserRole) => void;
}

export default function RoleToggle({ role, onRoleChange }: RoleToggleProps) {
  return (
    <div className="flex items-center rounded-full border border-border/60 bg-card/70 p-1 shadow-[var(--shadow-soft)] backdrop-blur-xl">
      <button
        onClick={() => onRoleChange("engineer")}
        className={`rounded-full px-4 py-2 text-[11px] font-mono uppercase tracking-[0.18em] transition-all duration-200 ${
          role === "engineer"
            ? "bg-primary text-primary-foreground shadow-[var(--shadow-soft)]"
            : "text-muted-foreground hover:text-foreground"
        }`}
      >
        Engineer
      </button>
      <button
        onClick={() => onRoleChange("executive")}
        className={`rounded-full px-4 py-2 text-[11px] font-mono uppercase tracking-[0.18em] transition-all duration-200 ${
          role === "executive"
            ? "bg-primary text-primary-foreground shadow-[var(--shadow-soft)]"
            : "text-muted-foreground hover:text-foreground"
        }`}
      >
        Executive
      </button>
    </div>
  );
}
