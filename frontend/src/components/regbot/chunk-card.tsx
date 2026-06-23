"use client";

import { ExternalLink } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Chunk } from "@/lib/api";
import { cn } from "@/lib/utils";

type ChunkCardProps = {
  chunk: Chunk;
  sourceUrls?: Record<string, string>;
  defaultOpen?: boolean;
};

function jurisdictionTags(meta: Record<string, unknown>): string[] {
  const raw = meta.jurisdiction;
  if (Array.isArray(raw)) return raw.map(String);
  if (raw) return [String(raw)];
  return [];
}

export function ChunkCard({ chunk, sourceUrls }: ChunkCardProps) {
  const meta = chunk.metadata ?? {};
  const tags = jurisdictionTags(meta);
  const docId = String(meta.document_id ?? meta.category ?? "");
  const sourceUrl = docId && sourceUrls ? sourceUrls[docId] : undefined;

  return (
    <Card className="border-border/80 shadow-sm">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="space-y-1">
            <CardTitle className="font-mono text-sm font-medium">
              {chunk.id}
            </CardTitle>
            <CardDescription className="text-xs">
              {String(meta.source ?? "?")} · p.{String(meta.page ?? "?")}
              {meta.category ? ` · ${String(meta.category)}` : ""}
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-1">
            {tags.map((t) => (
              <Badge key={t} variant="secondary" className="text-[10px]">
                {t}
              </Badge>
            ))}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {sourceUrl ? (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className={cn(buttonVariants({ variant: "outline", size: "sm" }), "inline-flex gap-2")}
          >
            <ExternalLink className="size-3.5" />
            Open original source
          </a>
        ) : null}
        <p className="text-muted-foreground line-clamp-6 whitespace-pre-wrap text-sm leading-relaxed">
          {(chunk.text ?? "").slice(0, 2000)}
        </p>
      </CardContent>
    </Card>
  );
}
