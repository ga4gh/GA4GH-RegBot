"use client";

import {
  BookOpenCheck,
  CircleCheck,
  Database,
  Globe2,
  RefreshCw,
  Settings2,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import type { JurisdictionOption } from "@/lib/api";

type SidebarProps = {
  storeDir: string;
  onStoreDirChange: (value: string) => void;
  canManageStore: boolean;
  storeJurisdictions: string[];
  jurisdictionOptions: JurisdictionOption[];
  corpusCount: number;
  manifestChunkCount: number;
  retrievalReady: boolean;
  llmHint: string;
  onRefresh: () => void;
  refreshing: boolean;
};

export function Sidebar({
  storeDir,
  onStoreDirChange,
  canManageStore,
  storeJurisdictions,
  jurisdictionOptions,
  corpusCount,
  manifestChunkCount,
  retrievalReady,
  llmHint,
  onRefresh,
  refreshing,
}: SidebarProps) {
  const labelByCode = Object.fromEntries(
    jurisdictionOptions.map((j) => [j.code, j.label]),
  );

  return (
    <aside className="border-border/80 bg-sidebar text-sidebar-foreground flex w-full flex-col border-b lg:w-72 lg:shrink-0 lg:border-r lg:border-b-0">
      <div className="space-y-4 p-4">
        {canManageStore ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Settings2 className="size-4 text-[#1b75bb]" />
              Store management
            </div>
            <div className="space-y-2">
              <Label
                htmlFor="store-dir"
                className="text-xs font-semibold tracking-wide uppercase"
              >
                Store directory
              </Label>
              <Input
                id="store-dir"
                value={storeDir}
                onChange={(e) => onStoreDirChange(e.target.value)}
                className="bg-background/70 font-mono text-xs"
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="w-full gap-2"
                onClick={onRefresh}
                disabled={refreshing}
              >
                <RefreshCw
                  className={refreshing ? "size-3.5 animate-spin" : "size-3.5"}
                />
                Refresh store
              </Button>
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-[#1b75bb]/12 bg-[#1b75bb]/[0.045] p-3.5">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-800">
              <ShieldCheck className="size-4 text-[#1b75bb]" />
              Public user workspace
            </div>
            <p className="text-muted-foreground mt-2 text-xs leading-5">
              Browse sources and run evidence-linked checks. Corpus management is protected
              for administrators.
            </p>
          </div>
        )}

        <Separator />

        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Globe2 className="size-4 shrink-0 text-[#1b75bb]" />
            Corpus coverage
          </div>
          <div className="border-border/60 bg-background/70 flex items-center gap-3 rounded-xl border p-3">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-sky-50 text-[#1b75bb]">
              <Database className="size-4" />
            </div>
            <div>
              <p className="text-lg leading-none font-semibold">{corpusCount}</p>
              <p className="text-muted-foreground mt-1 text-xs">source documents</p>
              <p className="text-muted-foreground mt-1 text-xs">
                {manifestChunkCount.toLocaleString()} tracked chunks
              </p>
            </div>
          </div>
          <div
            className={
              retrievalReady
                ? "flex items-start gap-2 rounded-lg bg-emerald-50 p-3 text-xs leading-5 text-emerald-800"
                : "flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-xs leading-5 text-amber-900"
            }
          >
            {retrievalReady ? (
              <CircleCheck className="mt-0.5 size-3.5 shrink-0" />
            ) : (
              <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
            )}
            <span>
              {retrievalReady
                ? "Retrieval index ready."
                : "Manifest available, but the Chroma retrieval index is not ready."}
            </span>
          </div>
          {storeJurisdictions.length > 0 ? (
            <div className="border-border/60 bg-muted/20 max-h-44 overflow-y-auto overscroll-contain rounded-md border p-2">
              <ul className="space-y-2 text-xs">
                {storeJurisdictions.map((code) => (
                  <li key={code} className="leading-relaxed break-words">
                    <span className="font-semibold">{code}</span>
                    <span className="text-muted-foreground">
                      {" "}
                      — {(labelByCode[code] ?? code).split(" — ").slice(1).join(" — ") ||
                        labelByCode[code]}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-muted-foreground text-xs leading-relaxed">
              No jurisdiction tags in the manifest yet. When ingesting policy, pick a region
              (SG, CN, JP, …) so retrieval can be scoped.
            </p>
          )}
        </div>

        {canManageStore ? (
          <>
            <Separator />
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-xs font-semibold tracking-wide uppercase">
                <Settings2 className="size-3.5" />
                System configuration
              </div>
              <p className="text-muted-foreground text-xs leading-relaxed break-words">
                {llmHint}
              </p>
            </div>
          </>
        ) : (
          <div className="text-muted-foreground flex items-start gap-2 rounded-lg bg-slate-50 p-3 text-xs leading-5">
            <BookOpenCheck className="mt-0.5 size-3.5 shrink-0 text-[#1b75bb]" />
            Select a workspace tab to browse sources, check consent text, or ask a policy
            question.
          </div>
        )}
      </div>
    </aside>
  );
}
