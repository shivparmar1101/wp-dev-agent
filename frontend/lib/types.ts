/**
 * Types mirroring the FastAPI/pydantic response models of the backend.
 * Keep these in sync with `backend/models/*`.
 */

export interface RateLimitInfo {
  limit?: number | null;
  remaining?: number | null;
  reset?: number | null;
  used?: number | null;
}

export interface Repository {
  id: number;
  name: string;
  full_name: string;
  owner: string;
  owner_avatar?: string | null;
  description?: string | null;
  private: boolean;
  fork: boolean;
  archived: boolean;
  disabled: boolean;
  visibility: string;
  default_branch: string;
  language?: string | null;
  html_url: string;
  updated_at?: string | null;
  pushed_at?: string | null;
  size_kb: number;
  stargazers_count: number;
  topics: string[];
}

export interface RepositoryListResponse {
  repositories: Repository[];
  page: number;
  per_page: number;
  has_more: boolean;
  total_returned: number;
  rate_limit?: RateLimitInfo | null;
  warnings: string[];
}

export interface SessionUser {
  login: string;
  name?: string | null;
  avatar?: string | null;
  scope?: string | null;
  created_at?: string;
}

export interface MeResponse {
  authenticated: boolean;
  user: SessionUser | null;
}

export interface HealthResponse {
  status: string;
  version: string;
  github_configured: boolean;
  ai_provider: string;
  ai_configured: boolean;
  environment: string;
}

export interface FileNode {
  name: string;
  path: string;
  type: "file" | "dir";
  size?: number | null;
  language?: string | null;
  category?: string | null;
  wordpress?: boolean;
  children: FileNode[];
}

export interface FileContent {
  path: string;
  content: string;
  size: number;
  language?: string | null;
  category: string;
  encoding: string;
  truncated: boolean;
  redacted: boolean;
  ref?: string | null;
}

export interface ThemeInfo {
  name: string;
  slug: string;
  location: string;
  version?: string | null;
  author?: string | null;
  description?: string | null;
  theme_type: "custom" | "child" | "parent" | "known" | "unknown";
  parent_theme?: string | null;
  block_theme: boolean;
  has_functions_php: boolean;
  text_domain?: string | null;
  headers: Record<string, string>;
}

export interface PluginInfo {
  name: string;
  slug: string;
  location: string;
  version?: string | null;
  author?: string | null;
  description?: string | null;
  text_domain?: string | null;
  main_file?: string | null;
  known: boolean;
  metadata_source: "plugin_header" | "directory" | "unknown";
  headers: Record<string, string>;
}

export type DetectionStatus = "detected" | "not_detected" | "unknown";

export interface ElementorDetection {
  elementor: DetectionStatus;
  elementor_pro: DetectionStatus;
  confidence: number;
  evidence: string[];
  indicators: string[];
  signals: Record<string, number>;
}

export interface IndexStats {
  files_indexed: number;
  chunks: number;
  files_skipped: number;
  skipped_reasons: Record<string, number>;
  embeddings_enabled: boolean;
  languages: Record<string, number>;
  built_at?: string | null;
}

export interface ProjectSummary {
  repository: string;
  owner: string;
  repo: string;
  branch: string;
  description?: string | null;
  project_types: string[];
  is_wordpress: boolean;
  wordpress_confidence: number;
  wordpress_indicators: string[];
  elementor: ElementorDetection;
  themes: ThemeInfo[];
  plugins: PluginInfo[];
  file_counts: Record<string, number>;
  total_files: number;
  source_files: number;
  languages: string[];
  tech: Record<string, boolean>;
  index?: IndexStats | null;
  notes: string[];
  scanned_at: string;
}

export interface StageStatus {
  id: string;
  label: string;
  status: "pending" | "running" | "done" | "error" | "skipped";
  detail?: string | null;
}

export interface ScanStatus {
  scan_id: string;
  owner: string;
  repo: string;
  status: "pending" | "running" | "completed" | "failed";
  progress: number;
  stages: StageStatus[];
  error?: string | null;
  error_details?: string | null;
  branch?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  summary?: ProjectSummary | null;
}

export interface SearchHit {
  file_path: string;
  score: number;
  start_line?: number | null;
  end_line?: number | null;
  snippet: string;
  match_type: string;
  language?: string | null;
  matched_terms: string[];
}

export interface SearchResponse {
  query: string;
  mode_requested: string;
  mode_used: string;
  hits: SearchHit[];
  total: number;
  took_ms: number;
  index?: IndexStats | null;
  notes: string[];
}

export interface CodeReference {
  file_path: string;
  start_line?: number | null;
  end_line?: number | null;
  snippet: string;
  language?: string | null;
  note?: string | null;
}

export interface AnalysisResponse {
  issue: string;
  relevant_files: CodeReference[];
  cause: string;
  suggested_solution: string;
  solution_language?: string | null;
  confidence: "High" | "Medium" | "Low" | "Unknown";
  explanation: string;
  raw: string;
  search_terms: string[];
  mode_used: string;
  files_consulted: string[];
  warnings: string[];
  provider: string;
  model?: string | null;
  created_at?: string | null;
}

export interface ChatMessageDto {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResponse {
  conversation_id?: string | null;
  analysis: AnalysisResponse;
}
