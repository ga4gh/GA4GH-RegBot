"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, LogOut, UserRound } from "lucide-react";
import Image from "next/image";
import { useRouter } from "next/navigation";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { BrowseTab } from "@/components/regbot/browse-tab";
import { ChatTab } from "@/components/regbot/chat-tab";
import { CheckTab } from "@/components/regbot/check-tab";
import { CorpusTab } from "@/components/regbot/corpus-tab";
import { IngestTab } from "@/components/regbot/ingest-tab";
import { Sidebar } from "@/components/regbot/sidebar";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  getCorpus,
  logout,
  getJurisdictions,
  getStoreMeta,
  type AuthUser,
  type ChatMessage,
} from "@/lib/api";

const DEFAULT_STORE = "./data/regbot_store";

/** Pure fetch: reads the API, touches no component state, never throws. */
async function fetchMeta(dir: string) {
  try {
    const [meta, corpus, jur] = await Promise.all([
      getStoreMeta(dir),
      getCorpus(),
      getJurisdictions(),
    ]);
    return { ok: true as const, meta, corpus, jur };
  } catch (e) {
    return {
      ok: false as const,
      error: e instanceof Error ? e.message : "Failed to connect to API",
    };
  }
}

export function RegBotApp({ user }: { user: AuthUser }) {
  const router = useRouter();
  const canManageStore = user.role === "admin";
  const [storeDir, setStoreDir] = useState(DEFAULT_STORE);
  const [jurisdictions, setJurisdictions] = useState<
    Awaited<ReturnType<typeof getJurisdictions>>
  >([]);
  const [storeJurisdictions, setStoreJurisdictions] = useState<string[]>([]);
  const [corpusCount, setCorpusCount] = useState(0);
  const [llmHint, setLlmHint] = useState("");
  // Starts true: the mount effect below is already fetching by first paint.
  const [refreshing, setRefreshing] = useState(true);

  const [lastConsent, setLastConsent] = useState("");
  const [lastJurisdictions, setLastJurisdictions] = useState<string[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);

  const [sourceUrls, setSourceUrls] = useState<Record<string, string>>({});
  const [apiError, setApiError] = useState<string | null>(null);
  const [signingOut, setSigningOut] = useState(false);

  // Fetching and applying are separate so the mount effect can await before it touches
  // state. `applyMeta` holds every setState; `fetchMeta` holds none.
  const applyMeta = useCallback(
    (result: Awaited<ReturnType<typeof fetchMeta>>) => {
      if (!result.ok) {
        setApiError(result.error);
        setRefreshing(false);
        return;
      }
      const { meta, corpus, jur } = result;
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
      setRefreshing(false);
    },
    [],
  );

  const refreshMeta = useCallback(
    async (dir?: string) => {
      applyMeta(await fetchMeta(dir ?? storeDir));
    },
    [storeDir, applyMeta],
  );

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const result = await fetchMeta(storeDir);
      if (cancelled) return;
      applyMeta(result);
    })();
    return () => {
      cancelled = true;
    };
  }, [storeDir, applyMeta]);

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
      "Evidence-linked regulatory navigation for genomic and health data policy.",
    [],
  );
  const identityLabel = canManageStore
    ? "Administrator"
    : user.username === "guest"
      ? "Public user"
      : user.username;

  const onLogout = useCallback(async () => {
    setSigningOut(true);
    try {
      await logout();
      router.replace("/login");
      router.refresh();
    } catch (reason) {
      setApiError(reason instanceof Error ? reason.message : "Could not sign out.");
      setSigningOut(false);
    }
  }, [router]);

  return (
    <div className="bg-background flex min-h-screen flex-col">
      <header className="border-border/70 bg-card/85 sticky top-0 z-20 border-b backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-3 sm:flex-row sm:items-center sm:justify-between lg:px-6">
          <div className="flex min-w-0 items-center gap-3 sm:gap-4">
            <Image
              src="/global-alliance-logo.svg"
              alt="Global Alliance for Genomics and Health"
              width={192}
              height={50}
              priority
              className="h-auto w-36 shrink-0 sm:w-40"
            />
            <div className="bg-border h-10 w-px shrink-0" aria-hidden="true" />
            <div className="min-w-0">
              <h1 className="text-lg font-semibold tracking-tight sm:text-xl">RegBot</h1>
              <p className="text-muted-foreground mt-0.5 hidden max-w-2xl text-xs leading-5 md:block lg:text-sm">
                {headerSubtitle}{" "}
                <span className="text-foreground/70 font-medium">Not legal advice.</span>
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center justify-between gap-2 sm:justify-end">
            <div className="bg-muted/60 flex items-center gap-2 rounded-full px-3 py-1.5">
              <UserRound className="text-muted-foreground size-4" />
              <span className="text-sm font-medium">{identityLabel}</span>
              <Badge
                variant={canManageStore ? "default" : "secondary"}
                className={canManageStore ? "" : "bg-emerald-50 text-emerald-700"}
              >
                {canManageStore ? "Admin access" : "Read only"}
              </Badge>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={signingOut}
              onClick={() => void onLogout()}
            >
              <LogOut className="size-3.5" />
              <span>Sign out</span>
            </Button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col lg:flex-row">
        <Sidebar
          storeDir={storeDir}
          onStoreDirChange={setStoreDir}
          canManageStore={canManageStore}
          storeJurisdictions={storeJurisdictions}
          jurisdictionOptions={jurisdictions}
          corpusCount={corpusCount}
          llmHint={llmHint}
          onRefresh={() => {
            setRefreshing(true);
            void refreshMeta(storeDir);
          }}
          refreshing={refreshing}
        />

        <main className="min-w-0 flex-1 p-4 lg:p-6">
          {apiError ? (
            <Alert variant="destructive" className="mb-6">
              <AlertCircle className="size-4" />
              <AlertTitle>API unavailable</AlertTitle>
              <AlertDescription className="whitespace-pre-line">{apiError}</AlertDescription>
            </Alert>
          ) : null}
          <Tabs defaultValue={canManageStore ? "ingest" : "corpus"} className="space-y-6">
            <TabsList className="bg-muted/50 h-auto flex-wrap justify-start gap-1 p-1">
              {canManageStore ? <TabsTrigger value="ingest">Ingest policy</TabsTrigger> : null}
              <TabsTrigger value="corpus">Corpus</TabsTrigger>
              <TabsTrigger value="browse">Browse by region</TabsTrigger>
              <TabsTrigger value="check">Check consent</TabsTrigger>
              <TabsTrigger value="chat">Ask a question</TabsTrigger>
            </TabsList>

            {canManageStore ? (
              <TabsContent value="ingest">
                <IngestTab
                  storeDir={storeDir}
                  jurisdictions={jurisdictions}
                  onSuccess={() => {
                    setRefreshing(true);
                    void refreshMeta(storeDir);
                  }}
                />
              </TabsContent>
            ) : null}
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
            <TabsContent value="check" keepMounted>
              <CheckTab
                storeDir={storeDir}
                jurisdictions={jurisdictions}
                sourceUrls={sourceUrls}
                defaultJurisdictions={lastJurisdictions}
                onAnalyzed={onAnalyzed}
              />
            </TabsContent>
            <TabsContent value="chat" keepMounted>
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
