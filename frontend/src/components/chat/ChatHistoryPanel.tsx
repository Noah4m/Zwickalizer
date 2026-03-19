import { MessageSquareText, Plus } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { UserRole } from "@/components/RoleToggle";
import type { ChatThread } from "@/components/chat/chat-data";

interface ChatHistoryPanelProps {
  activeThreadId: string;
  className?: string;
  disabled?: boolean;
  hideHeader?: boolean;
  threads: ChatThread[];
  onNewThread: () => void;
  onSelectThread: (threadId: string) => void;
}

function formatTimestamp(updatedAt: number) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(updatedAt);
}

function roleLabel(role: UserRole) {
  return role === "engineer" ? "ENG" : "EXEC";
}

export default function ChatHistoryPanel({
  activeThreadId,
  className,
  disabled = false,
  hideHeader = false,
  threads,
  onNewThread,
  onSelectThread,
}: ChatHistoryPanelProps) {
  return (
    <aside className={cn("flex h-full min-h-0 flex-col bg-card/45", className)}>
      {!hideHeader && (
        <div className="flex items-center justify-between gap-3 border-b border-border/60 px-4 py-4">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted-foreground">History</p>
            <p className="mt-1 text-sm text-muted-foreground">Restore previous analyses instantly.</p>
          </div>
          <button
            onClick={onNewThread}
            disabled={disabled}
            className="inline-flex items-center gap-2 rounded-full border border-border/70 bg-background/70 px-3 py-2 text-xs font-mono uppercase tracking-wider text-foreground transition-colors hover:border-primary disabled:opacity-50"
          >
            <Plus className="h-3.5 w-3.5" />
            New
          </button>
        </div>
      )}

      <ScrollArea className="flex-1">
        <div className="space-y-2 p-4">
          {threads.map((thread) => {
            const isActive = thread.id === activeThreadId;

            return (
              <button
                key={thread.id}
                onClick={() => onSelectThread(thread.id)}
                disabled={disabled}
                className={cn(
                  "w-full rounded-[24px] border p-4 text-left transition-all duration-200 disabled:opacity-50",
                  isActive
                    ? "border-primary/50 bg-primary/10 shadow-[var(--shadow-soft)]"
                    : "border-border/60 bg-background/65 hover:border-primary/40 hover:bg-background/85"
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-mono text-xs uppercase tracking-[0.18em] text-foreground">
                      {thread.title}
                    </p>
                    <p className="mt-1 text-sm text-muted-foreground break-words">
                      {thread.messages.at(-1)?.content ?? "Start a fresh analysis thread."}
                    </p>
                  </div>
                  <MessageSquareText className={cn("mt-0.5 h-4 w-4 shrink-0", isActive ? "text-primary" : "text-muted-foreground")} />
                </div>
                <div className="mt-3 flex items-center justify-between gap-2 text-[11px] font-mono uppercase tracking-[0.16em] text-muted-foreground">
                  <span className="rounded-full bg-secondary/80 px-2.5 py-1 text-secondary-foreground">{roleLabel(thread.role)}</span>
                  <span>{formatTimestamp(thread.updatedAt)}</span>
                </div>
              </button>
            );
          })}
        </div>
      </ScrollArea>
    </aside>
  );
}
