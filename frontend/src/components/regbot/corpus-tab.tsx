"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ExternalLink, Loader2 } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { getCorpus, type CorpusDocument, type JurisdictionOption } from "@/lib/api";
import { cn } from "@/lib/utils";

const TIER_LABELS: Record<string, string> = {
  P0: "P0 — GA4GH / REWS framework",
  P1: "P1 — GDPR & consent-code briefs",
  P2: "P2 — Regional law excerpts",
};

const TIER_STYLES: Record<string, string> = {
  P0: "bg-sky-500/15 text-sky-700 dark:text-sky-300",
  P1: "bg-violet-500/15 text-violet-700 dark:text-violet-300",
  P2: "bg-slate-500/15 text-slate-700 dark:text-slate-300",
};

type CorpusTabProps = {
  jurisdictions: JurisdictionOption[];
};

function CorpusDocRow({ doc }: { doc: CorpusDocument }) {
  return (
    <Card className="border-border/70">
      <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0 pb-2">
        <div className="min-w-0 flex-1">
          <CardTitle className="text-base leading-snug">{doc.title}</CardTitle>
          <CardDescription className="mt-1 font-mono text-xs">
            {doc.document_id}
          </CardDescription>
        </div>
        {doc.source_url ? (
          <a
            href={doc.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className={cn(
              buttonVariants({ variant: "outline", size: "sm" }),
              "inline-flex shrink-0 gap-2",
            )}
          >
            <ExternalLink className="size-3.5" />
            Open source
          </a>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-wrap items-center gap-2 pt-0">
        <Badge className={TIER_STYLES[doc.tier] ?? TIER_STYLES.P2}>{doc.tier}</Badge>
        {doc.jurisdiction.map((j) => (
          <Badge key={j} variant="secondary">
            {j}
          </Badge>
        ))}
        <span className="text-muted-foreground text-xs">
          ingested: {doc.ingested_at ? "yes" : "not yet"}
        </span>
      </CardContent>
    </Card>
  );
}

export function CorpusTab({ jurisdictions }: CorpusTabProps) {
  const [region, setRegion] = useState("ALL");
  const [docs, setDocs] = useState<CorpusDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getCorpus(region);
      setDocs(res.documents);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load corpus");
    } finally {
      setLoading(false);
    }
  }, [region]);

  useEffect(() => {
    void load();
  }, [load]);

  const byTier = useMemo(() => {
    const groups: Record<string, CorpusDocument[]> = { P0: [], P1: [], P2: [] };
    for (const doc of docs) {
      const tier = doc.tier.toUpperCase();
      groups[tier]?.push(doc);
    }
    return groups;
  }, [docs]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Corpus inventory</h2>
          <p className="text-muted-foreground mt-1 max-w-2xl text-sm">
            Regulatory corpus from <code className="text-xs">docs/corpus_manifest.yaml</code>.
            Open source links point to GA4GH pages, GDPR briefs, or statute references.
          </p>
        </div>
        <div className="w-full space-y-2 sm:w-72">
          <Label>Filter by jurisdiction</Label>
          <Select value={region} onValueChange={(v) => v && setRegion(v)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">All jurisdictions</SelectItem>
              {jurisdictions.map((j) => (
                <SelectItem key={j.code} value={j.code}>
                  {j.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {loading ? (
        <div className="text-muted-foreground flex items-center gap-2 text-sm">
          <Loader2 className="size-4 animate-spin" />
          Loading corpus…
        </div>
      ) : null}

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {!loading && !error && docs.length === 0 ? (
        <Alert>
          <AlertDescription>
            No corpus entries found for this filter.
          </AlertDescription>
        </Alert>
      ) : null}

      {(["P0", "P1", "P2"] as const).map((tier) => {
        const tierDocs = byTier[tier] ?? [];
        if (tierDocs.length === 0) return null;
        return (
          <section key={tier} className="space-y-3">
            <h3 className="text-muted-foreground text-sm font-semibold tracking-wide uppercase">
              {TIER_LABELS[tier] ?? tier}
            </h3>
            <div className="grid gap-3">
              {tierDocs.map((doc) => (
                <CorpusDocRow key={doc.document_id} doc={doc} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
