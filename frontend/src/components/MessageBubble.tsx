import { CircleUserRound } from "lucide-react";
import { ChatMessage } from "@/types/chat";

interface MessageBubbleProps {
  message: ChatMessage;
  isLoading?: boolean;
}

export default function MessageBubble({ message, isLoading }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-border/60 bg-background/80 text-muted-foreground shadow-[var(--shadow-soft)] backdrop-blur-xl">
          <CircleUserRound className="h-5 w-5" />
        </div>
      )}

      <div
        className={`max-w-[85%] rounded-[28px] border px-5 py-4 text-sm leading-relaxed shadow-[var(--shadow-soft)] backdrop-blur-xl ${
          isUser
            ? "bg-primary/10 border-primary/20 text-foreground"
            : "bg-card/75 border-border/60 text-foreground"
        }`}
      >
        {isLoading ? (
          <div className="flex items-center gap-1.5">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-primary animate-pulse [animation-delay:150ms]" />
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-primary animate-pulse [animation-delay:300ms]" />
            <span className="ml-2 text-muted-foreground font-mono text-xs">typing</span>
          </div>
        ) : (
          <>
            <p className="whitespace-pre-wrap">{message.content}</p>
            {message.toolCalls && message.toolCalls.length > 0 && (
              <div className="mt-3 pt-3 border-t border-border/50">
                {message.toolCalls.map((tc, i) => (
                  <div key={i} className="flex items-center gap-1.5 text-xs text-muted-foreground font-mono">
                    <span className="text-primary">▸</span>
                    <span>{tc.name}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {isUser && (
        <div className="mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-primary/20 bg-primary/10 text-primary shadow-[var(--shadow-soft)] backdrop-blur-xl">
          <CircleUserRound className="h-5 w-5" />
        </div>
      )}
    </div>
  );
}
