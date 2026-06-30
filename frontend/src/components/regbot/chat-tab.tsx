"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, MessageSquare, Send } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChunkCard } from "@/components/regbot/chunk-card";
import {
  chatFollowup,
  type ChatMessage,
  type Chunk,
  type JurisdictionOption,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type ChatTabProps = {
  storeDir: string;
  jurisdictions: JurisdictionOption[];
  consentText: string;
  lastJurisdictions: string[];
  messages: ChatMessage[];
  onMessagesChange: (messages: ChatMessage[]) => void;
  sourceUrls: Record<string, string>;
};

export function ChatTab({
  storeDir,
  jurisdictions,
  consentText,
  lastJurisdictions,
  messages,
  onMessagesChange,
  sourceUrls,
}: ChatTabProps) {
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedJurisdictions, setSelectedJurisdictions] = useState<string[]>(
    lastJurisdictions,
  );
  const [lastChunks, setLastChunks] = useState<Chunk[]>([]);
  const [lastScope, setLastScope] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (lastJurisdictions.length > 0) {
      setSelectedJurisdictions(lastJurisdictions);
    }
  }, [lastJurisdictions]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, lastChunks]);

  const toggleJurisdiction = (code: string) => {
    setSelectedJurisdictions((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code],
    );
  };

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
        consent_text: consentText,
        store_dir: storeDir || undefined,
        jurisdictions: selectedJurisdictions,
      });
      onMessagesChange([...nextMessages, { role: "assistant", content: res.reply }]);
      setLastChunks(res.chunks ?? []);
      setLastScope(res.scope ?? "");
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
    consentText,
    storeDir,
    selectedJurisdictions,
  ]);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Ask a question</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          Type a regulatory question in natural language. RegBot retrieves relevant policy
          excerpts and answers with chunk citations. Not legal advice.
        </p>
        {consentText.trim() ? (
          <p className="text-muted-foreground mt-1 text-xs">
            Optional consent context from your last Analyze is included.
          </p>
        ) : null}
      </div>

      <div className="space-y-2">
        <Label className="text-sm">Scope to jurisdiction(s)</Label>
        <div className="flex flex-wrap gap-3">
          {jurisdictions.map((j) => (
            <label
              key={j.code}
              className="border-border/80 bg-card/50 flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm"
            >
              <Checkbox
                checked={selectedJurisdictions.includes(j.code)}
                onCheckedChange={() => toggleJurisdiction(j.code)}
              />
              <span>{j.label}</span>
            </label>
          ))}
        </div>
        <p className="text-muted-foreground text-xs">
          Leave all unchecked to search all ingested policy.
        </p>
      </div>

      <div className="border-border/80 bg-muted/10 flex h-[min(50vh,480px)] flex-col rounded-xl border">
        <ScrollArea className="min-h-0 flex-1">
          <div className="space-y-4 p-4">
            {messages.length === 0 ? (
              <div className="text-muted-foreground flex flex-col items-center justify-center gap-2 py-16 text-center text-sm">
                <MessageSquare className="size-8 opacity-40" />
                e.g. What does GA4GH require for international data sharing?
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
                Retrieving policy context and drafting answer…
              </div>
            ) : null}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>
      </div>

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
          placeholder="Ask a regulatory question…"
          disabled={loading}
          className="flex-1"
        />
        <Button type="submit" disabled={loading || !prompt.trim()} className="gap-2">
          <Send className="size-4" />
          Send
        </Button>
      </form>

      {lastChunks.length > 0 ? (
        <details className="border-border/80 rounded-xl border p-4">
          <summary className="cursor-pointer text-sm font-medium">
            Retrieved policy excerpts
            {lastScope ? ` · ${lastScope}` : ""} · {lastChunks.length} chunk(s)
          </summary>
          <div className="mt-3 grid gap-3">
            {lastChunks.map((ch) => (
              <ChunkCard key={ch.id} chunk={ch} sourceUrls={sourceUrls} />
            ))}
          </div>
        </details>
      ) : null}
    </div>
  );
}
