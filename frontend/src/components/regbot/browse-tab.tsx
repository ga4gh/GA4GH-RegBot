"use client";

import { useCallback, useState } from "react";
import { Loader2, Search } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { ChunkCard } from "@/components/regbot/chunk-card";
import { getChunks, type Chunk, type JurisdictionOption } from "@/lib/api";

type BrowseTabProps = {
  storeDir: string;
  jurisdictions: JurisdictionOption[];
  sourceUrls: Record<string, string>;
};

export function BrowseTab({ storeDir, jurisdictions, sourceUrls }: BrowseTabProps) {
  const [region, setRegion] = useState(jurisdictions[0]?.code ?? "GA4GH");
  const [limit, setLimit] = useState(25);
  const [chunks, setChunks] = useState<Chunk[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loadedRegion, setLoadedRegion] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onLoad = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getChunks(region, limit, storeDir || undefined);
      setChunks(res.chunks);
      setTotal(res.total);
      setLoadedRegion(res.region);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load chunks");
      setChunks(null);
    } finally {
      setLoading(false);
    }
  }, [region, limit, storeDir]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Browse by region</h2>
        <p className="text-muted-foreground mt-1 max-w-2xl text-sm">
          View ingested policy chunks by jurisdiction without running a navigation check.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:max-w-2xl">
        <div className="space-y-2">
          <Label>Region / jurisdiction</Label>
          <Select value={region} onValueChange={(v) => v && setRegion(v)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {jurisdictions.map((j) => (
                <SelectItem key={j.code} value={j.code}>
                  {j.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Max chunks to show: {limit}</Label>
          <Slider
            min={5}
            max={80}
            step={1}
            value={[limit]}
            onValueChange={(v) => setLimit(Array.isArray(v) ? (v[0] ?? 25) : v)}
          />
        </div>
      </div>

      <Button type="button" onClick={onLoad} disabled={loading} className="gap-2">
        {loading ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <Search className="size-4" />
        )}
        Load chunks
      </Button>

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {chunks !== null ? (
        <div className="space-y-4">
          <h3 className="text-base font-medium">
            {loadedRegion} — {chunks.length} of {total} chunk(s)
          </h3>
          {chunks.length === 0 ? (
            <Alert>
              <AlertDescription>
                No chunks tagged `{loadedRegion}` in this store. Ingest a document with that
                jurisdiction or try another region.
              </AlertDescription>
            </Alert>
          ) : (
            <div className="grid gap-3">
              {chunks.map((ch) => (
                <ChunkCard key={ch.id} chunk={ch} sourceUrls={sourceUrls} />
              ))}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
