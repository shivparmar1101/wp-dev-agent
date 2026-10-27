import type {
  ChatResponse,
  FileContent,
  FileNode,
  HealthResponse,
  MeResponse,
  ProjectSummary,
  RepositoryListResponse,
  ScanStatus,
  SearchResponse,
} from "./types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  kind?: string;

  constructor(message: string, status: number, kind?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.kind = kind;
  }
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(`${API_URL}${path}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === "") continue;
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, query, headers, ...rest } = options;
  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      ...rest,
      credentials: "include",
      headers: {
        Accept: "application/json",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(headers || {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(
      "Could not reach the backend API. Is it running on " + API_URL + "?",
      0,
      "network",
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const detail =
      (payload as { detail?: string } | null)?.detail ||
      `Request failed with status ${response.status}`;
    const kind = (payload as { kind?: string } | null)?.kind;
    throw new ApiError(Array.isArray(detail) ? detail.join(" ") : detail, response.status, kind);
  }

  return payload as T;
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  me: () => request<MeResponse>("/api/auth/me"),
  logout: () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  loginUrl: () => `${API_URL}/api/auth/login`,

  repositories: (params: { page?: number; per_page?: number; q?: string; visibility?: string }) =>
    request<RepositoryListResponse>("/api/repositories", { query: params }),

  projects: () => request<ProjectSummary[]>("/api/projects"),
  project: (owner: string, repo: string) =>
    request<ProjectSummary>(`/api/projects/${owner}/${repo}`),

  tree: (owner: string, repo: string) =>
    request<FileNode>(`/api/projects/${owner}/${repo}/tree`),
  file: (owner: string, repo: string, path: string, ref?: string) =>
    request<FileContent>(`/api/projects/${owner}/${repo}/file`, {
      query: { path, ref },
    }),

  startScan: (owner: string, repo: string, branch?: string) =>
    request<ScanStatus>(`/api/scan/${owner}/${repo}`, {
      method: "POST",
      body: branch ? { branch } : {},
    }),
  startUrlScan: (url: string) =>
    request<ScanStatus>("/api/scan/url", {
      method: "POST",
      body: { url },
    }),
  scanStatus: (owner: string, repo: string) =>
    request<ScanStatus>(`/api/scan/${owner}/${repo}/status`),
  scanById: (scanId: string) => request<ScanStatus>(`/api/scan/${scanId}`),

  search: (owner: string, repo: string, query: string, mode: string, limit = 10) =>
    request<SearchResponse>(`/api/search/${owner}/${repo}`, {
      method: "POST",
      body: { query, mode, limit },
    }),

  chat: (
    owner: string,
    repo: string,
    message: string,
    history: { role: "user" | "assistant"; content: string }[],
    conversationId?: string | null,
  ) =>
    request<ChatResponse>(`/api/chat/${owner}/${repo}`, {
      method: "POST",
      body: { message, history, conversation_id: conversationId ?? null },
    }),
};
