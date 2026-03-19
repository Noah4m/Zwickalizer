import { Menu, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import ChatHistoryPanel from "@/components/chat/ChatHistoryPanel";
import type { ChatThread } from "@/components/chat/chat-data";

interface ChatHistorySheetProps {
  activeThreadId: string;
  disabled?: boolean;
  threads: ChatThread[];
  onNewThread: () => void;
  onSelectThread: (threadId: string) => void;
}

export default function ChatHistorySheet({
  activeThreadId,
  disabled = false,
  threads,
  onNewThread,
  onSelectThread,
}: ChatHistorySheetProps) {
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button
          variant="outline"
          size="icon"
          className="h-11 w-11 rounded-full border-border/60 bg-card/70 backdrop-blur-xl shadow-[var(--shadow-soft)] hover:bg-card"
          disabled={disabled}
          aria-label="Open chat history"
        >
          <Menu className="h-4 w-4" />
        </Button>
      </SheetTrigger>
      <SheetContent
        side="left"
        className="w-[92vw] max-w-[360px] border-border/60 bg-card/75 p-0 backdrop-blur-2xl shadow-[var(--shadow-elevated)]"
      >
        <SheetHeader className="border-b border-border/60 px-5 py-5 text-left">
          <div className="flex items-center justify-between gap-3 pr-10">
            <div>
              <SheetTitle className="font-mono text-base uppercase tracking-[0.22em] text-foreground">
                Conversations
              </SheetTitle>
              <SheetDescription className="mt-1 text-sm text-muted-foreground">
                Reopen previous threads and regenerate their analysis views.
              </SheetDescription>
            </div>
            <Button
              type="button"
              onClick={onNewThread}
              disabled={disabled}
              className="h-10 rounded-full px-4 font-mono text-[11px] uppercase tracking-[0.18em]"
            >
              <Plus className="h-3.5 w-3.5" />
              New
            </Button>
          </div>
        </SheetHeader>

        <div className="h-[calc(100%-96px)]">
          <ChatHistoryPanel
            activeThreadId={activeThreadId}
            threads={threads}
            onNewThread={onNewThread}
            onSelectThread={onSelectThread}
            disabled={disabled}
            hideHeader
            className="h-full border-0 bg-transparent"
          />
        </div>
      </SheetContent>
    </Sheet>
  );
}
