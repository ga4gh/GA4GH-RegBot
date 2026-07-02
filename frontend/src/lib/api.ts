const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

const API_START_HINT =
  "Start the API from the repo root: uvicorn src.api.app:app --reload --port 8000";

function formatApiError(status: number, detail: unknown): string {
  const text =
    typeof detail === "string"
      ? detail
      : detail != null
        ? JSON.stringify(detail)
        : "";
  if (
    status >= 500 &&
    (!text || text === "Internal Server Error" || text === "Internal Server Error.")
  ) {
    return `Cannot reach the RegBot API (${status}). ${API_START_HINT}`;
  }
  return text || `Request failed (${status})`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new Error(`Network error. ${API_START_HINT}`);
  }
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? body.message ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(formatApiError(res.status, detail));
  }
  return res.json() as Promise<T>;
}

export type JurisdictionOption = { code: string; label: string };

export type CorpusDocument = {
  document_id: string;
  title: string;
  tier: string;
  jurisdiction: string[];
  ingested_at?: string | null;
  source_url?: string | null;
};

export type Chunk = {
  id: string;
  text: string;
  metadata: Record<string, unknown>;
};

export type StoreMeta = {
  store_dir: string;
  jurisdictions: string[];
  corpus_document_count: number;
  llm_hint: string;
};

export type CheckResult = {
  report: Record<string, unknown>;
  chunks: Chunk[];
  scope: string;
  chunk_count: number;
};

export type ChatMessage = { role: "user" | "assistant"; content: string };

export function getJurisdictions() {
  return request<JurisdictionOption[]>("/api/meta/jurisdictions");
}

export function getStoreMeta(storeDir?: string) {
  const q = storeDir ? `?store_dir=${encodeURIComponent(storeDir)}` : "";
  return request<StoreMeta>(`/api/meta/store${q}`);
}

export function getCorpus(region?: string) {
  const q = region && region !== "ALL" ? `?region=${encodeURIComponent(region)}` : "";
  return request<{ documents: CorpusDocument[]; total: number }>(`/api/corpus${q}`);
}

export function getChunks(region: string, limit: number, storeDir?: string) {
  const params = new URLSearchParams({ region, limit: String(limit) });
  if (storeDir) params.set("store_dir", storeDir);
  return request<{ region: string; chunks: Chunk[]; total: number }>(
    `/api/chunks?${params}`,
  );
}

export async function ingestPolicy(
  file: File,
  opts: {
    reset: boolean;
    category: string;
    jurisdiction: string;
    storeDir?: string;
  },
) {
  const form = new FormData();
  form.append("file", file);
  form.append("reset", String(opts.reset));
  form.append("category", opts.category);
  form.append("jurisdiction", opts.jurisdiction);
  if (opts.storeDir) form.append("store_dir", opts.storeDir);
  return request<{ ok: boolean; jurisdiction: string; message: string }>("/api/ingest", {
    method: "POST",
    body: form,
  });
}

export function checkConsent(body: {
  consent_text: string;
  store_dir?: string;
  category?: string;
  jurisdictions: string[];
  top_k: number;
}) {
  return request<CheckResult>("/api/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function chatFollowup(body: {
  messages: ChatMessage[];
  chunks?: Chunk[];
  consent_text?: string;
  store_dir?: string;
  jurisdictions?: string[];
  top_k?: number;
  category?: string;
}) {
  return request<{ reply: string; chunks?: Chunk[]; scope?: string }>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
