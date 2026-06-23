"use client";

import { useCallback, useEffect, useState } from "react";
import { FileUp, Loader2 } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ingestPolicy, type JurisdictionOption } from "@/lib/api";

type IngestTabProps = {
  storeDir: string;
  jurisdictions: JurisdictionOption[];
  onSuccess?: () => void;
};

export function IngestTab({ storeDir, jurisdictions, onSuccess }: IngestTabProps) {
  const [file, setFile] = useState<File | null>(null);
  const [reset, setReset] = useState(false);
  const [category, setCategory] = useState("");
  const [jurisdiction, setJurisdiction] = useState("GA4GH");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: "ok" | "err"; text: string } | null>(
    null,
  );

  useEffect(() => {
    if (jurisdictions.some((j) => j.code === "GA4GH")) {
      setJurisdiction("GA4GH");
    } else if (jurisdictions[0]) {
      setJurisdiction(jurisdictions[0].code);
    }
  }, [jurisdictions]);

  const onIngest = useCallback(async () => {
    if (!file) return;
    setLoading(true);
    setMessage(null);
    try {
      const res = await ingestPolicy(file, {
        reset,
        category,
        jurisdiction,
        storeDir: storeDir || undefined,
      });
      setMessage({
        type: res.ok ? "ok" : "err",
        text: res.message,
      });
      if (res.ok) onSuccess?.();
    } catch (e) {
      setMessage({ type: "err", text: e instanceof Error ? e.message : "Ingest failed" });
    } finally {
      setLoading(false);
    }
  }, [file, reset, category, jurisdiction, storeDir, onSuccess]);

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Ingest policy</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          Upload a PDF or plain-text policy file into the local Chroma store. Tag a
          jurisdiction so retrieval can be scoped by region.
        </p>
      </div>

      <div className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="policy-file">Policy PDF or .txt</Label>
          <Input
            id="policy-file"
            type="file"
            accept=".pdf,.txt"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>

        <div className="flex items-center gap-2">
          <Checkbox
            id="reset-store"
            checked={reset}
            onCheckedChange={(v) => setReset(v === true)}
          />
          <Label htmlFor="reset-store" className="font-normal">
            Reset store before ingest
          </Label>
        </div>

        <div className="space-y-2">
          <Label htmlFor="category">Category label (optional)</Label>
          <Input
            id="category"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            placeholder="e.g. consent-policy"
          />
        </div>

        <div className="space-y-2">
          <Label>Jurisdiction for this document</Label>
          <Select value={jurisdiction} onValueChange={(v) => v && setJurisdiction(v)}>
            <SelectTrigger className="w-full">
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

        <Button
          type="button"
          disabled={!file || loading}
          onClick={onIngest}
          className="gap-2"
        >
          {loading ? <Loader2 className="size-4 animate-spin" /> : <FileUp className="size-4" />}
          Ingest
        </Button>

        {message ? (
          <Alert variant={message.type === "err" ? "destructive" : "default"}>
            <AlertDescription>{message.text}</AlertDescription>
          </Alert>
        ) : null}
      </div>
    </div>
  );
}
