"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, Scale } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { BrowseTab } from "@/components/regbot/browse-tab";
import { ChatTab } from "@/components/regbot/chat-tab";
import { CheckTab } from "@/components/regbot/check-tab";
import { CorpusTab } from "@/components/regbot/corpus-tab";
import { IngestTab } from "@/components/regbot/ingest-tab";
import { Sidebar } from "@/components/regbot/sidebar";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  getCorpus,
  getJurisdictions,
  getStoreMeta,
  type ChatMessage,
} from "@/lib/api";

const DEFAULT_STORE = "./data/regbot_store";

export function RegBotApp() {
  const [storeDir, setStoreDir] = useState(DEFAULT_STORE);
  const [jurisdictions, setJurisdictions] = useState<
    Awaited<ReturnType<typeof getJurisdictions>>
  >([]);
  const [storeJurisdictions, setStoreJurisdictions] = useState<string[]>([]);
  const [corpusCount, setCorpusCount] = useState(0);
  const [llmHint, setLlmHint] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const [lastConsent, setLastConsent] = useState("");
  const [lastJurisdictions, setLastJurisdictions] = useState<string[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);

  const [sourceUrls, setSourceUrls] = useState<Record<string, string>>({});
  const [apiError, setApiError] = useState<string | null>(null);

  const refreshMeta = useCallback(async (dir?: string) => {
    setRefreshing(true);
    try {
      const [meta, corpus, jur] = await Promise.all([
        getStoreMeta(dir ?? storeDir),
        getCorpus(),
        getJurisdictions(),
      ]);
      setStoreJurisdictions(meta.jurisdictions);
      setCorpusCount(meta.corpus_document_count);
      setLlmHint(meta.llm_hint);
      setJurisdictions(jur);
      const urls: Record<string, string> = {};
      for (const doc of corpus.documents) {
        if (doc.document_id && doc.source_url) {
          urls[doc.document_id] = doc.source_url;
        }
      }
      setSourceUrls(urls);
      setApiError(null);
    } catch (e) {
      setApiError(e instanceof Error ? e.message : "Failed to connect to API");
    } finally {
      setRefreshing(false);
    }
  }, [storeDir]);

  useEffect(() => {
    void refreshMeta();
  }, [refreshMeta]);

  const onAnalyzed = useCallback(
    (payload: {
      consentText: string;
      jurisdictions: string[];
    }) => {
      setLastConsent(payload.consentText);
      setLastJurisdictions(payload.jurisdictions);
      setChatMessages([]);
    },
    [],
  );

  const headerSubtitle = useMemo(
    () =>
      "Prototype assistant: ingest GA4GH-style policy excerpts, retrieve hybrid context, and draft a citation-oriented regulatory navigation note.",
    [],
  );

  return (
    <div className="bg-background flex min-h-screen flex-col">
      <header className="border-border/80 bg-card/50 border-b backdrop-blur-sm">
        <div className="mx-auto flex max-w-7xl items-start gap-3 px-4 py-4 lg:px-6">
          <div className="bg-primary/10 text-primary flex size-10 shrink-0 items-center justify-center rounded-xl">
            <Scale className="size-5" />
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">GA4GH-RegBot</h1>
            <p className="text-muted-foreground mt-0.5 max-w-3xl text-sm">
              {headerSubtitle}{" "}
              <span className="text-foreground/70 font-medium">Not legal advice.</span>
            </p>
          </div>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col lg:flex-row">
        <Sidebar
          storeDir={storeDir}
          onStoreDirChange={setStoreDir}
          storeJurisdictions={storeJurisdictions}
          jurisdictionOptions={jurisdictions}
          corpusCount={corpusCount}
          llmHint={llmHint}
          onRefresh={() => void refreshMeta(storeDir)}
          refreshing={refreshing}
        />

        <main className="min-w-0 flex-1 p-4 lg:p-6">
          {apiError ? (
            <Alert variant="destructive" className="mb-6">
              <AlertCircle className="size-4" />
              <AlertTitle>API unavailable</AlertTitle>
              <AlertDescription>{apiError}</AlertDescription>
            </Alert>
          ) : null}
          <Tabs defaultValue="ingest" className="space-y-6">
            <TabsList className="bg-muted/50 h-auto flex-wrap justify-start gap-1 p-1">
              <TabsTrigger value="ingest">Ingest policy</TabsTrigger>
              <TabsTrigger value="corpus">Corpus</TabsTrigger>
              <TabsTrigger value="browse">Browse by region</TabsTrigger>
              <TabsTrigger value="check">Check consent</TabsTrigger>
              <TabsTrigger value="chat">Ask a question</TabsTrigger>
            </TabsList>

            <TabsContent value="ingest">
              <IngestTab
                storeDir={storeDir}
                jurisdictions={jurisdictions}
                onSuccess={() => void refreshMeta(storeDir)}
              />
            </TabsContent>
            <TabsContent value="corpus">
              <CorpusTab jurisdictions={jurisdictions} />
            </TabsContent>
            <TabsContent value="browse">
              <BrowseTab
                storeDir={storeDir}
                jurisdictions={jurisdictions}
                sourceUrls={sourceUrls}
              />
            </TabsContent>
            <TabsContent value="check">
              <CheckTab
                storeDir={storeDir}
                jurisdictions={jurisdictions}
                sourceUrls={sourceUrls}
                defaultJurisdictions={lastJurisdictions}
                onAnalyzed={onAnalyzed}
              />
            </TabsContent>
            <TabsContent value="chat">
              <ChatTab
                storeDir={storeDir}
                jurisdictions={jurisdictions}
                consentText={lastConsent}
                lastJurisdictions={lastJurisdictions}
                messages={chatMessages}
                onMessagesChange={setChatMessages}
                sourceUrls={sourceUrls}
              />
            </TabsContent>
          </Tabs>
        </main>
      </div>
    </div>
  );
}
