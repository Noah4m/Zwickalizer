import { useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, Users } from "lucide-react";
import RoleToggle, { type UserRole } from "@/components/RoleToggle";
import MessageBubble from "@/components/MessageBubble";
import AnalysisVault from "@/components/AnalysisVault";
import ChatComposer from "@/components/chat/ChatComposer";
import ChatEmptyState from "@/components/chat/ChatEmptyState";
import ChatHistorySheet from "@/components/chat/ChatHistorySheet";
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
  const [role, setRole] = useState<UserRole>("engineer");
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const activeThread = useMemo(
    () => threads.find((thread) => thread.id === activeThreadId) ?? threads[0],
    [threads, activeThreadId],
  );

  const messages = activeThread?.messages ?? [];
  const hasResponse = messages.some((message) => message.role === "assistant");
  const analysisData = useMemo(() => deriveAnalysisData(messages), [messages]);

  const patchThread = (threadId: string, updater: (thread: ChatThread) => ChatThread) => {
    setThreads((currentThreads) =>
      sortThreads(
        currentThreads.map((thread) => (thread.id === threadId ? updater(thread) : thread)),
      ),
    );
  };

  const handleRoleChange = (nextRole: UserRole) => {
    setRole(nextRole);
    if (!activeThread) return;

    patchThread(activeThread.id, (thread) => ({
      ...thread,
      role: nextRole,
      updatedAt: Date.now(),
    }));
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
    setRole(thread.role);
    setInput("");
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
          history: history.map((message) => ({ role: message.role, content: message.content })),
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
            analysis: Array.isArray(data.analysis) && data.analysis.length > 0 ? data.analysis : undefined,
            timestamp: new Date(),
          },
        ],
        updatedAt: Date.now(),
      }));
    } catch (error) {
      const message =
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
            content: `⚠ Error: ${message}`,
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
              <ChatHistorySheet
                activeThreadId={activeThread?.id ?? ""}
                threads={threads}
                onNewThread={handleNewThread}
                onSelectThread={handleSelectThread}
                disabled={loading}
              />
              <div className="flex h-11 w-11 items-center justify-center rounded-full bg-primary/12 text-primary shadow-[var(--shadow-soft)]">
                <Users className="h-5 w-5" />
              </div>
              <div>
                <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted-foreground">Materials Chat</p>
                <p className="mt-1 text-sm text-muted-foreground">Ask a colleague-style assistant about test results and trends.</p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <div className="hidden items-center gap-2 rounded-full border border-border/60 bg-background/55 px-3 py-2 text-xs text-muted-foreground md:flex">
                <Sparkles className="h-3.5 w-3.5 text-primary" />
                Regenerated outputs for each thread
              </div>
              <RoleToggle role={role} onRoleChange={handleRoleChange} />
            </div>
          </header>

          <div className="flex flex-1 min-h-0 bg-background/30">
            <motion.div
              className="flex min-h-0 min-w-0 flex-col"
              animate={{ width: hasResponse ? "44%" : "100%" }}
              transition={{ duration: 0.45, ease: [0.4, 0, 0.2, 1] }}
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
            </motion.div>

            <AnimatePresence>
              {hasResponse && (
                <motion.div
                  initial={{ width: 0, opacity: 0 }}
                  animate={{ width: "56%", opacity: 1 }}
                  exit={{ width: 0, opacity: 0 }}
                  transition={{ duration: 0.45, ease: [0.4, 0, 0.2, 1] }}
                  className="hidden min-h-0 min-w-0 border-l border-border/60 bg-background/35 md:block"
                >
                  <AnalysisVault data={analysisData} />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </div>
  );
}
