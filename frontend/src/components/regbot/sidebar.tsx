"use client";

import { Database, Globe2, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import type { JurisdictionOption } from "@/lib/api";

type SidebarProps = {
  storeDir: string;
  onStoreDirChange: (value: string) => void;
  storeJurisdictions: string[];
  jurisdictionOptions: JurisdictionOption[];
  corpusCount: number;
  llmHint: string;
  onRefresh: () => void;
  refreshing: boolean;
};

export function Sidebar({
  storeDir,
  onStoreDirChange,
  storeJurisdictions,
  jurisdictionOptions,
  corpusCount,
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
        <div className="space-y-2">
          <Label htmlFor="store-dir" className="text-xs font-semibold tracking-wide uppercase">
            Store directory
          </Label>
          <Input
            id="store-dir"
            value={storeDir}
            onChange={(e) => onStoreDirChange(e.target.value)}
            className="bg-background/50 font-mono text-xs"
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="w-full gap-2"
            onClick={onRefresh}
            disabled={refreshing}
          >
            <RefreshCw className={refreshing ? "size-3.5 animate-spin" : "size-3.5"} />
            Refresh store
          </Button>
        </div>

        <Separator />

        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Globe2 className="size-4 shrink-0" />
            Corpus by region
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
              No jurisdiction tags in the store yet. When ingesting policy, pick a region
              (SG, CN, JP, …) so retrieval can be scoped.
            </p>
          )}
          <p className="text-muted-foreground flex items-start gap-1.5 text-xs leading-relaxed">
            <Database className="mt-0.5 size-3.5 shrink-0" />
            <span>
              <strong>{corpusCount}</strong> documents in corpus manifest
            </span>
          </p>
        </div>

        <Separator />

        <p className="text-muted-foreground text-xs leading-relaxed break-words">{llmHint}</p>
      </div>
    </aside>
  );
}
