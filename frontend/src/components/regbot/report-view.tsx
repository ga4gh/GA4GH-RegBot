"use client";

import { AlertTriangle, FileText, Quote, Users } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

type ReportViewProps = {
  report: Record<string, unknown>;
};

type EvidenceEntry = {
  chunk_id?: string;
  resolved?: boolean;
  source?: string;
  page?: number;
  document_id?: string;
  section?: string;
  jurisdiction?: string | string[];
  framework?: string;
  quote?: string;
  relevance?: string;
  governance_hint?: string;
};

function asString(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

const REVIEW_REASON_LABELS: Record<string, string> = {
  weak_retrieval: "Not enough policy context was retrieved",
  low_overlap: "Recommendations were not sufficiently supported by the cited text",
  grounding_failed: "Citation grounding checks did not pass",
};

function HumanReviewBanner({ report }: { report: Record<string, unknown> }) {
  if (report.needs_human_review !== true) return null;
  const reason = typeof report.review_reason === "string" ? report.review_reason : "";
  const details = typeof report.review_details === "string" ? report.review_details : "";

  return (
    <Alert variant="destructive">
      <AlertTriangle className="size-4" />
      <AlertTitle>Escalate to human review</AlertTitle>
      <AlertDescription className="space-y-1">
        <p>{REVIEW_REASON_LABELS[reason] ?? "This report needs human review."}</p>
        {details ? <p className="text-xs opacity-90">{details}</p> : null}
        <p className="text-xs opacity-90">
          RegBot surfaces information for DPO / IRB / DAC review and does not issue
          compliance decisions.
        </p>
      </AlertDescription>
    </Alert>
  );
}

function EvidenceCard({ entry }: { entry: EvidenceEntry }) {
  if (entry.resolved === false) {
    return (
      <div className="border-destructive/40 bg-destructive/5 rounded-md border border-dashed p-3">
        <p className="text-destructive text-xs">
          Cited chunk{" "}
          <span className="font-mono">{entry.chunk_id}</span> was not in the retrieved
          evidence set — treat this citation as ungrounded.
        </p>
      </div>
    );
  }

  const jurisdictions = Array.isArray(entry.jurisdiction)
    ? entry.jurisdiction
    : entry.jurisdiction
      ? [entry.jurisdiction]
      : [];

  return (
    <div className="bg-background/60 space-y-2 rounded-md border p-3">
      <div className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
        <FileText className="size-3.5 shrink-0" />
        <span className="font-medium">{entry.source ?? entry.document_id ?? "source"}</span>
        {typeof entry.page === "number" && entry.page > 0 ? (
          <span>p.{entry.page}</span>
        ) : null}
        {entry.section ? <span className="italic">§ {entry.section}</span> : null}
        {jurisdictions.map((code) => (
          <Badge key={code} variant="secondary" className="text-[10px]">
            {code}
          </Badge>
        ))}
        {entry.framework ? (
          <Badge variant="outline" className="text-[10px]">
            {entry.framework}
          </Badge>
        ) : null}
      </div>

      {entry.quote ? (
        <blockquote className="border-primary/40 text-foreground/90 border-l-2 pl-3 text-sm italic">
          <Quote className="text-muted-foreground mr-1 inline size-3" />
          {entry.quote}
        </blockquote>
      ) : null}

      {entry.relevance ? (
        <p className="text-muted-foreground text-xs">{entry.relevance}</p>
      ) : null}

      {entry.governance_hint ? (
        <p className="text-muted-foreground flex items-start gap-1.5 text-xs">
          <Users className="mt-0.5 size-3 shrink-0" />
          <span>
            <span className="font-medium">Usually reviewed by:</span>{" "}
            {entry.governance_hint}
          </span>
        </p>
      ) : null}

      {entry.chunk_id ? (
        <p className="text-muted-foreground/70 font-mono text-[10px]">{entry.chunk_id}</p>
      ) : null}
    </div>
  );
}

function Recommendations({ items }: { items: unknown }) {
  if (!Array.isArray(items) || items.length === 0) return null;

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold">Recommendations</h4>
      {items.map((item, i) => {
        const rec = item as Record<string, unknown>;
        const evidence = Array.isArray(rec.evidence)
          ? (rec.evidence as EvidenceEntry[])
          : [];
        const ids = Array.isArray(rec.evidence_chunk_ids) ? rec.evidence_chunk_ids : [];

        return (
          <Card key={i} className="bg-muted/30">
            <CardContent className="space-y-3 pt-4">
              <p className="text-sm leading-relaxed">{asString(rec.text)}</p>

              {evidence.length > 0 ? (
                <div className="space-y-2">
                  {evidence.map((entry, j) => (
                    <EvidenceCard key={entry.chunk_id ?? j} entry={entry} />
                  ))}
                </div>
              ) : ids.length > 0 ? (
                // Older reports without Phase 3 enrichment: show bare ids.
                <div className="flex flex-wrap gap-1">
                  {ids.map((id) => (
                    <Badge
                      key={String(id)}
                      variant="outline"
                      className="font-mono text-[10px]"
                    >
                      {String(id)}
                    </Badge>
                  ))}
                </div>
              ) : (
                <p className="text-muted-foreground text-xs italic">
                  No cited evidence — this recommendation is ungrounded.
                </p>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

export function ReportView({ report }: ReportViewProps) {
  const studyType = report.study_type;
  const coverage = report.coverage;
  const missingElements = report.missing_elements;
  const notes = report.notes;
  const grounding = (report.grounding ?? {}) as Record<string, unknown>;

  return (
    <div className="space-y-4">
      <HumanReviewBanner report={report} />

      <div className="flex flex-wrap items-center gap-2">
        {studyType ? <Badge className="bg-primary/90">{asString(studyType)}</Badge> : null}
        {coverage ? (
          <Badge variant="secondary">coverage: {asString(coverage)}</Badge>
        ) : null}
        {typeof grounding.ok === "boolean" ? (
          <Badge variant={grounding.ok ? "secondary" : "destructive"}>
            grounding: {grounding.ok ? "passed" : "failed"}
          </Badge>
        ) : null}
        {typeof report.model === "string" ? (
          <Badge variant="outline" className="text-[10px]">
            {report.model}
          </Badge>
        ) : null}
      </div>

      <Recommendations items={report.recommendations} />

      {Array.isArray(missingElements) && missingElements.length > 0 ? (
        <div className="space-y-2">
          <h4 className="text-sm font-semibold">
            Topics not clearly addressed in the submitted text
          </h4>
          <ul className="text-muted-foreground list-inside list-disc space-y-1 text-sm">
            {missingElements.map((f, i) => (
              <li key={i}>{asString(f)}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {Array.isArray(grounding.issues) && grounding.issues.length > 0 ? (
        <div className="space-y-2">
          <h4 className="text-sm font-semibold">Grounding issues</h4>
          <ul className="text-muted-foreground list-inside list-disc space-y-1 text-xs">
            {(grounding.issues as unknown[]).map((issue, i) => (
              <li key={i}>{asString(issue)}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {typeof notes === "string" && notes.trim() ? (
        <p className="text-muted-foreground text-xs leading-relaxed">{notes}</p>
      ) : null}

      <Separator />

      <details className="group">
        <summary className="text-muted-foreground cursor-pointer text-sm font-medium">
          Raw JSON report
        </summary>
        <pre className="bg-muted/50 mt-2 max-h-96 overflow-auto rounded-lg p-4 font-mono text-xs">
          {JSON.stringify(report, null, 2)}
        </pre>
      </details>
    </div>
  );
}
