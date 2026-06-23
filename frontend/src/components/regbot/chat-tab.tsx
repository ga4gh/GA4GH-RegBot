"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, MessageSquare, Send } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { chatFollowup, type ChatMessage, type Chunk } from "@/lib/api";
import { cn } from "@/lib/utils";

type ChatTabProps = {
  storeDir: string;
  chunks: Chunk[];
  consentText: string;
  lastJurisdictions: string[];
  messages: ChatMessage[];
  onMessagesChange: (messages: ChatMessage[]) => void;
};

export function ChatTab({
  storeDir,
  chunks,
  consentText,
  lastJurisdictions,
  messages,
  onMessagesChange,
}: ChatTabProps) {
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const onSend = useCallback(async () => {
    const text = prompt.trim();
    if (!text || loading) return;
    const nextMessages: ChatMessage[] = [...messages, { role: "user", content: text }];
    onMessagesChange(nextMessages);
    setPrompt("");
    setLoading(true);
    setError(null);
    try {
      const res = await chatFollowup({
        messages: nextMessages,
        chunks: chunks as Chunk[],
        consent_text: consentText,
        store_dir: storeDir || undefined,
      });
      onMessagesChange([...nextMessages, { role: "assistant", content: res.reply }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Chat failed");
      onMessagesChange(messages);
      setPrompt(text);
    } finally {
      setLoading(false);
    }
  }, [
    prompt,
    loading,
    messages,
    onMessagesChange,
    chunks,
    consentText,
    storeDir,
  ]);

  if (chunks.length === 0) {
    return (
      <div className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Ask follow-up</h2>
          <p className="text-muted-foreground mt-1 text-sm">
            Exploratory Q&A on retrieved policy context. Not legal advice.
          </p>
        </div>
        <Alert>
          <AlertDescription>
            Run <strong>Analyze</strong> on the Check consent tab first to load chunks into
            this session.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="flex h-[min(70vh,640px)] flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Ask follow-up</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          Uses the same retrieved policy chunks as your last Analyze. Exploratory only — not
          programmatically grounded like the JSON report.
        </p>
        {lastJurisdictions.length > 0 ? (
          <p className="text-muted-foreground mt-1 text-xs">
            Last analysis jurisdictions: {lastJurisdictions.join(", ")}
          </p>
        ) : null}
      </div>

      <ScrollArea className="border-border/80 bg-muted/10 min-h-0 flex-1 rounded-xl border">
        <div className="space-y-4 p-4">
          {messages.length === 0 ? (
            <div className="text-muted-foreground flex flex-col items-center justify-center gap-2 py-16 text-center text-sm">
              <MessageSquare className="size-8 opacity-40" />
              Ask a question about the retrieved policy context.
            </div>
          ) : (
            messages.map((msg, i) => (
              <div
                key={i}
                className={cn(
                  "flex",
                  msg.role === "user" ? "justify-end" : "justify-start",
                )}
              >
                <div
                  className={cn(
                    "max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm",
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-card border-border/80 border",
                  )}
                >
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                </div>
              </div>
            ))
          )}
          {loading ? (
            <div className="text-muted-foreground flex items-center gap-2 text-sm">
              <Loader2 className="size-4 animate-spin" />
              Thinking…
            </div>
          ) : null}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void onSend();
        }}
      >
        <Input
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Question about the retrieved policy context…"
          disabled={loading}
          className="flex-1"
        />
        <Button type="submit" disabled={loading || !prompt.trim()} className="gap-2">
          <Send className="size-4" />
          Send
        </Button>
      </form>
    </div>
  );
}
