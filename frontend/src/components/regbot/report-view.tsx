"use client";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

type ReportViewProps = {
  report: Record<string, unknown>;
};

function asString(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function Recommendations({ items }: { items: unknown }) {
  if (!Array.isArray(items) || items.length === 0) return null;
  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold">Recommendations</h4>
      {items.map((item, i) => {
        const rec = item as Record<string, unknown>;
        const ids = rec.evidence_chunk_ids;
        return (
          <Card key={i} className="bg-muted/30">
            <CardContent className="space-y-2 pt-4">
              <p className="text-sm leading-relaxed">{asString(rec.text)}</p>
              {Array.isArray(ids) && ids.length > 0 ? (
                <div className="flex flex-wrap gap-1">
                  {ids.map((id) => (
                    <Badge key={String(id)} variant="outline" className="font-mono text-[10px]">
                      {String(id)}
                    </Badge>
                  ))}
                </div>
              ) : null}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

export function ReportView({ report }: ReportViewProps) {
  const studyType = report.study_type;
  const summary = report.summary ?? report.overall_assessment;
  const findings = report.findings ?? report.issues;
  const recommendations = report.recommendations;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {studyType ? (
          <Badge className="bg-primary/90">{asString(studyType)}</Badge>
        ) : null}
        {report.grounding_strict != null ? (
          <Badge variant="secondary">
            grounding: {String(report.grounding_strict)}
          </Badge>
        ) : null}
      </div>

      {summary ? (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground text-sm leading-relaxed">
              {asString(summary)}
            </p>
          </CardContent>
        </Card>
      ) : null}

      <Recommendations items={recommendations} />

      {Array.isArray(findings) && findings.length > 0 ? (
        <div className="space-y-2">
          <h4 className="text-sm font-semibold">Findings</h4>
          <ul className="text-muted-foreground list-inside list-disc space-y-1 text-sm">
            {findings.map((f, i) => (
              <li key={i}>{asString(f)}</li>
            ))}
          </ul>
        </div>
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
