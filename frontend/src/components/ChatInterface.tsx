import { useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, MessageSquareText } from "lucide-react";
import BrandMark from "@/components/BrandMark";
import RoleToggle, { type UserRole } from "@/components/RoleToggle";
import MessageBubble from "@/components/MessageBubble";
import AnalysisVault from "@/components/AnalysisVault";
import ChatComposer from "@/components/chat/ChatComposer";
import ChatEmptyState from "@/components/chat/ChatEmptyState";
import ChatHistorySheet from "@/components/chat/ChatHistorySheet";
import OutlierWorkbench from "@/components/outliers/OutlierWorkbench";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { ChatMessage } from "@/types/chat";
import {
  createEmptyThread,
  deriveAnalysisData,
  getThreadTitle,
  type ChatThread,
} from "@/components/chat/chat-data";

const initialThread = createEmptyThread("engineer");
const CHAT_REQUEST_TIMEOUT_MS = 120000;

function sortThreads(threads: ChatThread[]) {
  return [...threads].sort((a, b) => b.updatedAt - a.updatedAt);
}

export default function ChatInterface() {
  const [threads, setThreads] = useState<ChatThread[]>(() => [initialThread]);
  const [activeThreadId, setActiveThreadId] = useState(initialThread.id);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const role: UserRole = "engineer";
  const [activeWorkspace, setActiveWorkspace] = useState<"chat" | "outliers">("chat");
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const activeThread = useMemo(
    () => threads.find((thread) => thread.id === activeThreadId) ?? threads[0],
    [threads, activeThreadId],
  );

  const messages = activeThread?.messages ?? [];
  const hasResponse = messages.some((message) => message.role === "assistant");
  const analysisData = useMemo(() => deriveAnalysisData(messages), [messages]);

  const currentTestId = useMemo(() => {
    const latestAssistant = [...messages].reverse().find((m) => m.role === "assistant");
    const toolCall = [...(latestAssistant?.toolCalls ?? [])]
      .reverse()
      .find((t) => t.name === "db_find_tests");
    const tests = (toolCall?.result as Record<string, unknown>)?.tests;
    if (Array.isArray(tests) && tests.length > 0) {
      return String((tests[0] as Record<string, unknown>).testId ?? "");
    }
    return undefined;
  }, [messages]);

  const patchThread = (threadId: string, updater: (thread: ChatThread) => ChatThread) => {
    setThreads((currentThreads) =>
      sortThreads(
        currentThreads.map((thread) => (thread.id === threadId ? updater(thread) : thread)),
      ),
    );
  };

  const handleNewThread = () => {
    if (loading) return;

    const thread = createEmptyThread(role);
    setThreads((currentThreads) => sortThreads([thread, ...currentThreads]));
    setActiveThreadId(thread.id);
    setInput("");
    textareaRef.current?.focus();
  };

  const handleSelectThread = (threadId: string) => {
    if (loading) return;

    const thread = threads.find((item) => item.id === threadId);
    if (!thread) return;

    setActiveThreadId(threadId);
    setInput("");
  };

  const sendMessage = async (text: string, history: ChatMessage[]) => {
    if (!activeThread) return;

    setLoading(true);
    try {
      const controller = new AbortController();
      const timeoutId = window.setTimeout(() => controller.abort(), CHAT_REQUEST_TIMEOUT_MS);
      const res = await fetch(`/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          message: text,
          role,
          history: history.map((m) => ({ role: m.role, content: m.content })),
        }),
      });
      window.clearTimeout(timeoutId);

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      patchThread(activeThread.id, (thread) => ({
        ...thread,
        role,
        messages: [
          ...thread.messages,
          {
            role: "assistant",
            content: data.answer,
            toolCalls: data.tool_calls || [],
            analysis:
              Array.isArray(data.analysis) && data.analysis.length > 0
                ? data.analysis
                : undefined,
            timestamp: new Date(),
          },
        ],
        updatedAt: Date.now(),
      }));
    } catch (error) {
      const errorMessage =
        error instanceof DOMException && error.name === "AbortError"
          ? `Request timed out after ${CHAT_REQUEST_TIMEOUT_MS / 1000} seconds. Check \`docker compose logs -f frontend backend agent\`.`
          : error instanceof Error
            ? error.message
            : "Unknown error";

      patchThread(activeThread.id, (thread) => ({
        ...thread,
        messages: [
          ...thread.messages,
          {
            role: "assistant",
            content: `⚠ Error: ${errorMessage}`,
            toolCalls: [],
            analysis: undefined,
            timestamp: new Date(),
          },
        ],
        updatedAt: Date.now(),
      }));
    } finally {
      setLoading(false);
      requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }));
    }
  };

  const send = async () => {
    const text = input.trim();
    if (!text || loading || !activeThread) return;

    const userMsg: ChatMessage = { role: "user", content: text, timestamp: new Date() };
    const history = activeThread.messages;

    patchThread(activeThread.id, (thread) => ({
      ...thread,
      title: thread.messages.length === 0 ? getThreadTitle(text) : thread.title,
      role,
      messages: [...thread.messages, userMsg],
      updatedAt: Date.now(),
    }));

    setInput("");
    await sendMessage(text, history);
  };

  const handleSendPrompt = async (message: string) => {
    if (loading || !activeThread) return;

    const userMsg: ChatMessage = { role: "user", content: message, timestamp: new Date() };
    const history = activeThread.messages;

    patchThread(activeThread.id, (thread) => ({
      ...thread,
      messages: [...thread.messages, userMsg],
      updatedAt: Date.now(),
    }));

    await sendMessage(message, history);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send();
    }
  };

  return (
    <div className="relative flex h-screen overflow-hidden bg-background text-foreground">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,hsl(var(--primary)/0.15),transparent_28%),radial-gradient(circle_at_top_right,hsl(var(--accent)/0.14),transparent_26%),linear-gradient(180deg,hsl(var(--background)),hsl(var(--background)))]" />

      <div className="relative flex min-w-0 flex-1 p-3 md:p-5">
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-[34px] border border-border/60 bg-card/45 shadow-[var(--shadow-elevated)] backdrop-blur-2xl">
          <header className="flex items-center justify-between gap-4 border-b border-border/60 px-4 py-4 md:px-6">
            <div className="flex items-center gap-3">
              {activeWorkspace === "chat" ? (
                <ChatHistorySheet
                  activeThreadId={activeThread?.id ?? ""}
                  threads={threads}
                  onNewThread={handleNewThread}
                  onSelectThread={handleSelectThread}
                  disabled={loading}
                />
              ) : (
                <div className="flex h-11 w-11 items-center justify-center rounded-full border border-border/60 bg-card/70 text-muted-foreground shadow-[var(--shadow-soft)] backdrop-blur-xl">
                  <AlertTriangle className="h-4 w-4" />
                </div>
              )}
              {activeWorkspace === "chat" ? (
                <BrandMark compact />
              ) : (
                <BrandMark compact />
              )}
            </div>

            <div className="flex items-center gap-3">
              <Tabs value={activeWorkspace} onValueChange={(value) => setActiveWorkspace(value as "chat" | "outliers")}>
                <TabsList className="h-auto rounded-full border border-border/60 bg-card/70 p-1 shadow-[var(--shadow-soft)] backdrop-blur-xl">
                  <TabsTrigger value="chat" className="rounded-full px-4 py-2 text-[11px] font-mono uppercase tracking-[0.18em] data-[state=active]:shadow-[var(--shadow-soft)]">
                    <MessageSquareText className="mr-2 h-3.5 w-3.5" />
                    Chat
                  </TabsTrigger>
                  <TabsTrigger value="outliers" className="rounded-full px-4 py-2 text-[11px] font-mono uppercase tracking-[0.18em] data-[state=active]:shadow-[var(--shadow-soft)]">
                    <AlertTriangle className="mr-2 h-3.5 w-3.5" />
                    Outliers
                  </TabsTrigger>
                </TabsList>
              </Tabs>
              <RoleToggle />
            </div>
          </header>

          {activeWorkspace === "chat" ? (
            <div className="flex flex-1 min-h-0 bg-background/30">
              <div
                className={cn(
                  "flex min-h-0 min-w-0 flex-col",
                  hasResponse ? "w-full md:w-[44%]" : "w-full",
                )}
              >
                <div className="flex-1 overflow-y-auto px-4 py-6 md:px-6">
                  {messages.length === 0 && <ChatEmptyState onSelectExample={setInput} />}

                  <div className="mx-auto flex max-w-[860px] flex-col gap-4">
                    {messages.map((message, index) => (
                      <MessageBubble key={index} message={message} />
                    ))}
                    {loading && <MessageBubble message={{ role: "assistant", content: "" }} isLoading />}
                    <div ref={bottomRef} />
                  </div>
                </div>

                <ChatComposer
                  input={input}
                  loading={loading}
                  textareaRef={textareaRef}
                  onChange={setInput}
                  onKeyDown={onKeyDown}
                  onSend={() => void send()}
                />
              </div>

              <AnimatePresence>
                {hasResponse && (
                  <motion.div
                    initial={{ opacity: 0, x: 24 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 24 }}
                    transition={{ duration: 0.45, ease: [0.4, 0, 0.2, 1] }}
                    className="hidden min-h-0 min-w-0 border-l border-border/60 bg-background/35 md:block md:w-[56%]"
                  >
                    <AnalysisVault
                      data={analysisData}
                      currentTestId={currentTestId}
                      onSendPrompt={handleSendPrompt}
                    />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ) : (
            <div className="min-h-0 flex-1 bg-background/30">
              <OutlierWorkbench />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
