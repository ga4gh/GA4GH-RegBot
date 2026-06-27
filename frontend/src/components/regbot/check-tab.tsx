"use client";

import { useCallback, useState } from "react";
import { Download, Loader2, Sparkles } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import { ChunkCard } from "@/components/regbot/chunk-card";
import { ReportView } from "@/components/regbot/report-view";
import {
  checkConsent,
  type ChatMessage,
  type CheckResult,
  type Chunk,
  type JurisdictionOption,
} from "@/lib/api";

type CheckTabProps = {
  storeDir: string;
  jurisdictions: JurisdictionOption[];
  sourceUrls: Record<string, string>;
  defaultJurisdictions: string[];
  onAnalyzed: (payload: {
    result: CheckResult;
    consentText: string;
    jurisdictions: string[];
    chunks: Chunk[];
  }) => void;
};

export function CheckTab({
  storeDir,
  jurisdictions,
  sourceUrls,
  defaultJurisdictions,
  onAnalyzed,
}: CheckTabProps) {
  const [consentText, setConsentText] = useState("");
  const [category, setCategory] = useState("");
  const [selectedJurisdictions, setSelectedJurisdictions] =
    useState<string[]>(defaultJurisdictions);
  const [topK, setTopK] = useState(8);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CheckResult | null>(null);

  const toggleJurisdiction = (code: string) => {
    setSelectedJurisdictions((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code],
    );
  };

  const onAnalyze = useCallback(async () => {
    if (!consentText.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await checkConsent({
        consent_text: consentText,
        store_dir: storeDir || undefined,
        category: category.trim() || undefined,
        jurisdictions: selectedJurisdictions,
        top_k: topK,
      });
      setResult(res);
      onAnalyzed({
        result: res,
        consentText,
        jurisdictions: selectedJurisdictions,
        chunks: res.chunks,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  }, [consentText, storeDir, category, selectedJurisdictions, topK, onAnalyzed]);

  const downloadReport = () => {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result.report, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "regbot_report.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Check consent</h2>
        <p className="text-muted-foreground mt-1 max-w-2xl text-sm">
          Paste consent or data-use language. Hybrid retrieval finds relevant policy excerpts;
          the LLM returns a citation-oriented JSON report. Not legal advice.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="consent">Consent or data-use text</Label>
            <Textarea
              id="consent"
              value={consentText}
              onChange={(e) => setConsentText(e.target.value)}
              rows={12}
              placeholder="Paste participant consent or data-use language here…"
              className="min-h-[240px] resize-y font-mono text-sm"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="filter-cat">Only use policy category (optional)</Label>
            <Input
              id="filter-cat"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label>Scope to jurisdiction(s)</Label>
            <p className="text-muted-foreground text-xs">
              Leave all unchecked to search all ingested policy.
            </p>
            <div className="border-border/80 bg-muted/20 grid max-h-48 gap-2 overflow-y-auto rounded-lg border p-3 sm:grid-cols-2">
              {jurisdictions.map((j) => (
                <label
                  key={j.code}
                  className="flex cursor-pointer items-start gap-2 text-sm"
                >
                  <Checkbox
                    checked={selectedJurisdictions.includes(j.code)}
                    onCheckedChange={() => toggleJurisdiction(j.code)}
                  />
                  <span className="leading-tight">{j.code}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <Label>Retrieved chunks: {topK}</Label>
            <Slider
              min={3}
              max={16}
              step={1}
              value={[topK]}
              onValueChange={(v) => setTopK(Array.isArray(v) ? (v[0] ?? 8) : v)}
            />
          </div>

          <Button
            type="button"
            onClick={onAnalyze}
            disabled={loading || !consentText.trim()}
            className="gap-2"
          >
            {loading ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Sparkles className="size-4" />
            )}
            Analyze
          </Button>

          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
        </div>

        <div className="space-y-4">
          {result ? (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="font-semibold">Report</h3>
                  <p className="text-muted-foreground text-xs">
                    Retrieval scope: {result.scope} · {result.chunk_count} chunk(s) used
                  </p>
                </div>
                <Button variant="outline" size="sm" onClick={downloadReport} className="gap-2">
                  <Download className="size-3.5" />
                  Download JSON
                </Button>
              </div>
              <ReportView report={result.report} />
              <details className="group" open>
                <summary className="cursor-pointer text-sm font-medium">
                  Retrieved policy excerpts
                </summary>
                <div className="mt-3 grid gap-3">
                  {result.chunks.length === 0 ? (
                    <Alert>
                      <AlertDescription>
                        No chunks matched this query and jurisdiction filter.
                      </AlertDescription>
                    </Alert>
                  ) : (
                    result.chunks.map((ch) => (
                      <ChunkCard key={ch.id} chunk={ch} sourceUrls={sourceUrls} />
                    ))
                  )}
                </div>
              </details>
            </>
          ) : (
            <div className="border-border/60 bg-muted/20 text-muted-foreground flex min-h-[320px] items-center justify-center rounded-xl border border-dashed p-8 text-center text-sm">
              Run Analyze to generate a compliance report from retrieved policy context.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}