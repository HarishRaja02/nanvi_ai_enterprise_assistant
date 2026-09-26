import { getDemoFallbackResponse } from "./lib/demoFallback";

export type ApiClientOptions = {
  baseUrl?: string;
  getAccessToken?: () => Promise<string | null>;
  onUnauthorized?: () => void;
};

export type UserIdentity = {
  subject: string;
  issuer: string;
  email?: string | null;
  name?: string | null;
  tenant_id?: string | null;
  department?: string | null;
  roles: string[];
};

export type ChatSource = {
  reference_id: string;
  source_type: string;
  display_name: string;
  title?: string | null;
  location?: string | null;
  page?: number | null;
  sheet?: string | null;
  timestamp?: string | null;
  mime_type?: string | null;
  href?: string | null;
};

export type ChatResponse = {
  conversation_id: string;
  answer: string;
  capability: string;
  sources: ChatSource[];
  trace: string[];
  history: Array<{ role: "user" | "assistant"; content: string; created_at: string }>;
  report_id?: string | null;
};

export type VoiceResponse = {
  conversation_id: string;
  answer: string;
  spoken_text: string;
  important_points: string[];
  capability: string;
  sources: ChatSource[];
  trace: string[];
  history: Array<{ role: "user" | "assistant"; content: string; created_at: string }>;
  report_id?: string | null;
};

export type Conversation = {
  conversation_id: string;
  title?: string | null;
  created_at?: string;
  updated_at?: string;
  message_count?: number;
};

export type UploadDocumentResponse = {
  status: string;
  filename: string;
  path: string;
  size_bytes: number;
  message: string;
};

export type HistoryResponse = { conversations: Conversation[] };
export type SourceReference = ChatSource;
export type DownloadUrlResponse = { download_url: string };

export class ApiError extends Error {
  readonly status: number;
  readonly retryAfter?: number;

  constructor(message: string, status: number, retryAfter?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

/**
 * Thin, typed boundary to FastAPI. The UI never treats local role state as authorization.
 * Production identity/permissions always come from the backend.
 */
export class NanviApiClient {
  private readonly baseUrl: string;
  private readonly getAccessToken?: () => Promise<string | null>;
  private readonly onUnauthorized?: () => void;

  constructor(options: ApiClientOptions = {}) {
    const rawEnvBase = (typeof import.meta !== "undefined" && import.meta.env?.VITE_API_BASE_URL) || "";
    const envBase = (typeof rawEnvBase === "string" ? rawEnvBase : "").trim();
    let defaultBase = "/api";
    if (envBase) {
      defaultBase = envBase.endsWith("/api") ? envBase : `${envBase.replace(/\/$/, "")}/api`;
    }
    this.baseUrl = (options.baseUrl ?? defaultBase).replace(/\/$/, "");
    this.getAccessToken = options.getAccessToken;
    this.onUnauthorized = options.onUnauthorized;
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const token = this.getAccessToken ? await this.getAccessToken() : null;
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    if (token) headers.set("Authorization", `Bearer ${token}`);

    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, { ...init, headers, credentials: "same-origin" });
    } catch {
      const fallback = getDemoFallbackResponse<T>(path, init);
      if (fallback !== undefined) return fallback;
      throw new ApiError("Nanvi is unreachable. Check your connection and try again.", 0);
    }

    if (response.status === 401) {
      this.onUnauthorized?.();
    }

if (!response.ok) {
  let detail = "Nanvi could not complete the request.";

  try {
    const body = (await response.json()) as { detail?: string };

    if (typeof body.detail === "string" && body.detail.trim()) {
      detail = body.detail;
    }
  } catch {
    // Preserve the safe generic message when the backend returns non-JSON content.
  }

  const retryAfterHeader = response.headers.get("Retry-After");
  const retryAfter = retryAfterHeader
    ? Number.parseInt(retryAfterHeader, 10)
    : undefined;

  if (response.status === 429) {
    detail = `Too many requests. Please try again${
      retryAfter ? ` in ${retryAfter}s` : " shortly"
    }.`;
  }

  if (response.status >= 500) {
    detail = "Nanvi is temporarily unavailable. Please try again.";
  }

  throw new ApiError(
    detail,
    response.status,
    Number.isFinite(retryAfter) ? retryAfter : undefined
  );
}

    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }

  me() { return this.request<UserIdentity>("/auth/me"); }

  chat(query: string, conversationId?: string, ragEnabled: boolean = true) {
    return this.request<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({ query, conversation_id: conversationId, rag_enabled: ragEnabled }),
    });
  }

  voiceRespond(query: string, conversationId?: string, ragEnabled: boolean = true) {
    return this.request<VoiceResponse>("/voice/respond", {
      method: "POST",
      body: JSON.stringify({ query, conversation_id: conversationId, rag_enabled: ragEnabled }),
    });
  }

  voiceTranscribe(audioBase64: string, mimeType: string = "audio/webm", filename: string = "recording.webm") {
    return this.request<{ text: string; confidence: number }>("/voice/transcribe", {
      method: "POST",
      body: JSON.stringify({ audio_base64: audioBase64, mime_type: mimeType, filename }),
    });
  }

  async voiceSynthesize(text: string, profileId: string = "nanvi-warm", signal?: AbortSignal): Promise<Blob> {
    const token = this.getAccessToken ? await this.getAccessToken() : null;
    const headers = new Headers();
    headers.set("Content-Type", "application/json");
    if (token) headers.set("Authorization", `Bearer ${token}`);

    const response = await fetch(`${this.baseUrl}/voice/synthesize`, {
      method: "POST",
      headers,
      body: JSON.stringify({ text, profile_id: profileId }),
      credentials: "same-origin",
      signal,
    });

    if (!response.ok) {
      throw new ApiError("Failed to synthesize neural voice", response.status);
    }

    return await response.blob();
  }

  uploadDocument(filename: string, contentBase64: string) {
    return this.request<UploadDocumentResponse>("/chat/upload", {
      method: "POST",
      body: JSON.stringify({ filename, content_base64: contentBase64 }),
    });
  }

  history() { return this.request<HistoryResponse>("/chat/history"); }

  conversation(conversationId: string) {
    return this.request<{ conversation_id: string; messages: Array<{ role: "user" | "assistant"; content: string; created_at: string }> }>(
      `/chat/history/${encodeURIComponent(conversationId)}`
    );
  }

  source(referenceId: string) {
    return this.request<SourceReference>(`/sources/${encodeURIComponent(referenceId)}`);
  }

  reportDownloadUrl(reportId: string) {
    return this.request<DownloadUrlResponse>(`/reports/${encodeURIComponent(reportId)}/download-url`, { method: "POST" });
  }

  devToken(role: string, department: string, name?: string, email?: string) {
    return this.request<{ access_token: string; token_type: string; expires_in: number }>("/dev/token", {
      method: "POST",
      body: JSON.stringify({ role, department, name: name ?? "Dev User", email: email ?? "dev@nanvi.local" }),
    });
  }

  emailStatus() {
    return this.request<EmailStatusResponse>("/email/status");
  }

  googleAuthUrl(redirectUri?: string) {
    const q = redirectUri ? `?redirect_uri=${encodeURIComponent(redirectUri)}` : "";
    return this.request<{ auth_url: string }>(`/email/oauth/google/url${q}`);
  }

  connectGoogleMailbox(code: string, state?: string, redirectUri?: string) {
    return this.request<{ status: string; account: EmailAccount }>("/email/oauth/google/callback", {
      method: "POST",
      body: JSON.stringify({ code, state, redirect_uri: redirectUri }),
    });
  }

  disconnectEmail(accountId?: string) {
    return this.request<{ status: string }>("/email/disconnect", {
      method: "POST",
      body: JSON.stringify({ account_id: accountId }),
    });
  }

  manualConnectEmail(emailAddress: string, displayName?: string, refreshToken?: string) {
    return this.request<{ status: string; account: EmailAccount }>("/email/manual-connect", {
      method: "POST",
      body: JSON.stringify({ email_address: emailAddress, display_name: displayName, refresh_token: refreshToken }),
    });
  }

  // Company folder settings
  getCompanyFolder() {
    return this.request<CompanyFolderResponse>("/settings/company-folder");
  }

  updateCompanyFolder(path: string) {
    return this.request<CompanyFolderUpdateResponse>("/settings/company-folder", {
      method: "PUT",
      body: JSON.stringify({ path }),
    });
  }

  browseDirectory(path: string) {
    return this.request<BrowseDirectoryResponse>("/settings/company-folder/browse", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
  }

  listProviders() {
    return this.request<{ providers: ProviderPublic[] }>("/connections/providers");
  }

  listConnectionCategories() {
    return this.request<string[]>("/connections/categories");
  }

  listConnections(params?: { provider?: string; scope?: string; status?: string; q?: string }) {
    const qp = new URLSearchParams();
    if (params?.provider) qp.set("provider", params.provider);
    if (params?.scope) qp.set("scope", params.scope);
    if (params?.status) qp.set("status", params.status);
    if (params?.q) qp.set("q", params.q);
    const qs = qp.toString();
    return this.request<ConnectionListResponse>(`/connections${qs ? `?${qs}` : ""}`);
  }

  getConnection(id: string) {
    return this.request<ConnectionPublic>(`/connections/${encodeURIComponent(id)}`);
  }

  createConnection(req: CreateConnectionRequest) {
    return this.request<ConnectionPublic>("/connections", {
      method: "POST",
      body: JSON.stringify(req),
    });
  }

  validateConnection(req: ValidateConnectionRequest) {
    return this.request<TestConnectionResponse>("/connections/validate", {
      method: "POST",
      body: JSON.stringify(req),
    });
  }

  testConnection(id: string) {
    return this.request<TestConnectionResponse>(`/connections/${encodeURIComponent(id)}/test`, {
      method: "POST",
    });
  }

  updateConnection(id: string, req: UpdateConnectionRequest) {
    return this.request<ConnectionPublic>(`/connections/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(req),
    });
  }

  deleteConnection(id: string) {
    return this.request<void>(`/connections/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
  }

  getOAuthAuthorizeUrl(provider: string, scopeLevel = "user", redirectAfter?: string) {
    const qp = new URLSearchParams({ scope_level: scopeLevel });
    if (redirectAfter) qp.set("redirect_after", redirectAfter);
    return this.request<{ authorization_url: string }>(`/connections/oauth/${encodeURIComponent(provider)}/authorize?${qp.toString()}`);
  }

  listConnectionAuditEvents() {
    return this.request<any[]>("/connections/audit/events");
  }
}


export type EmailAccount = {
  id: string;
  email_address: string;
  display_name: string;
  provider: string;
  avatar_url?: string | null;
  connected_at: string;
  last_synced_at?: string | null;
  is_active?: boolean;
};

export type EmailStatusResponse = {
  connected: boolean;
  account: EmailAccount | null;
  has_enterprise_fallback?: boolean;
};

export type CompanyFolderResponse = {
  path: string;
  exists: boolean;
  folder_count: number;
  file_count: number;
};

export type CompanyFolderUpdateResponse = {
  status: string;
  path: string;
  exists: boolean;
  folder_count: number;
  file_count: number;
  indexed_files: number;
  message: string;
};

export type BrowseDirectoryEntry = {
  name: string;
  path: string;
  is_dir: boolean;
};

export type BrowseDirectoryResponse = {
  path: string;
  parent?: string | null;
  entries: BrowseDirectoryEntry[];
  error?: string;
};

export type ProviderPublic = {
  id: string;
  name: string;
  categories: string[];
  icon: string;
  description: string;
  auth_type: string;
  capabilities: string[];
  available: boolean;
  available_reason: string;
  configuration_schema: Record<string, any>;
};

export type ConnectionPublic = {
  id: string;
  provider: string;
  display_name: string;
  account_identifier?: string | null;
  scope_level: "user" | "organization";
  status: "CONNECTED" | "DISCONNECTED" | "ERROR" | "EXPIRED" | "REAUTH_REQUIRED" | "TESTING";
  status_reason?: string | null;
  granted_scopes: string[];
  metadata_safe: Record<string, any>;
  credential_type?: string | null;
  last_tested_at?: string | null;
  last_used_at?: string | null;
  last_synced_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  created_by?: string | null;
  owner_user_id?: string | null;
};

export type ConnectionListResponse = {
  connections: ConnectionPublic[];
  total: number;
};

export type CreateConnectionRequest = {
  provider: string;
  display_name: string;
  scope_level?: "user" | "organization";
  config: Record<string, any>;
};

export type ValidateConnectionRequest = {
  provider: string;
  config: Record<string, any>;
};

export type UpdateConnectionRequest = {
  display_name?: string | null;
  config?: Record<string, any> | null;
};

export type TestConnectionResponse = {
  ok: boolean;
  message: string;
  details?: Record<string, any>;
};

