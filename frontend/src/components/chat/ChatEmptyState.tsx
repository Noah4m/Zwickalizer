import BrandMark from "@/components/BrandMark";

interface ChatEmptyStateProps {
  onSelectExample: (query: string) => void;
}

const exampleQueries = [
  "Give me a summary for Test 3",
  "Is there degradation in the tensile strength of Material 3?",
];

export default function ChatEmptyState({ onSelectExample }: ChatEmptyStateProps) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center select-none">
      <div className="rounded-[32px] border border-border/60 bg-card/60 px-8 py-10 shadow-[var(--shadow-elevated)] backdrop-blur-2xl">
        <BrandMark />
        <div className="mt-8 flex w-full max-w-md flex-col gap-3">
          {exampleQueries.map((query) => (
            <button
              key={query}
              onClick={() => onSelectExample(query)}
              className="rounded-[22px] border border-border/60 bg-background/55 px-4 py-3 text-left text-sm text-foreground shadow-[var(--shadow-soft)] transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:bg-background/85"
            >
              {query}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
