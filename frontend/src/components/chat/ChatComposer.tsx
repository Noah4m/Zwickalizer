import { SendHorizontal } from "lucide-react";
import type { KeyboardEvent, RefObject } from "react";

interface ChatComposerProps {
  input: string;
  loading: boolean;
  textareaRef: RefObject<HTMLTextAreaElement>;
  onChange: (value: string) => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onSend: () => void;
}

export default function ChatComposer({ input, loading, textareaRef, onChange, onKeyDown, onSend }: ChatComposerProps) {
  return (
    <div className="px-4 pb-5 pt-3 shrink-0 md:px-6 md:pb-6">
      <div className="mx-auto flex max-w-[860px] items-end gap-3 rounded-[32px] border border-border/60 bg-card/70 p-3 shadow-[var(--shadow-elevated)] backdrop-blur-2xl">
        <textarea
          ref={textareaRef}
          className="min-h-[56px] flex-1 resize-none rounded-[24px] border border-transparent bg-background/40 px-4 py-3 text-sm leading-relaxed text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-primary/30"
          rows={2}
          placeholder="Ask about materials, trends, comparisons…"
          value={input}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <button
          onClick={onSend}
          disabled={loading || !input.trim()}
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-[var(--shadow-soft)] transition-all hover:scale-105 hover:opacity-95 disabled:opacity-40"
          aria-label="Send message"
        >
          <SendHorizontal className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
