import { DEMO_MODE } from "./config";
import type {
  ChatResponse,
  VoiceResponse,
  ProviderPublic,
  ConnectionPublic,
  CompanyFolderResponse,
  CompanyFolderUpdateResponse,
  BrowseDirectoryResponse,
  EmailStatusResponse,
} from "../api";

export function getDemoFallbackResponse<T>(path: string, init?: RequestInit): T | undefined {
  if (!DEMO_MODE) return undefined;

  const cleanPath = path.split("?")[0].replace(/\/$/, "");
  const method = (init?.method || "GET").toUpperCase();

  if (cleanPath === "/auth/me") {
    return {
      sub: "demo-user-1",
      email: "demo.executive@nanvi.enterprise",
      name: "Demo Executive",
      roles: ["CEO", "Manager", "IT Admin"],
      department: "Leadership",
    } as unknown as T;
  }

  if (cleanPath === "/chat/history") {
    return { conversations: [] } as unknown as T;
  }

  if (cleanPath.startsWith("/chat/conversations/")) {
    const id = cleanPath.split("/").pop() || "demo-conv";
    return {
      conversation_id: id,
      messages: [],
    } as unknown as T;
  }

  if (cleanPath === "/email/status") {
    const status: EmailStatusResponse = {
      connected: false,
      account: null,
      has_enterprise_fallback: true,
    };
    return status as unknown as T;
  }

  if (cleanPath === "/email/oauth/google/url") {
    const redirectParam = typeof window !== "undefined" ? window.location.origin : "";
    return {
      auth_url: `${redirectParam}?connected=google&status=success`,
    } as unknown as T;
  }

  if (cleanPath === "/email/disconnect") {
    return { status: "disconnected" } as unknown as T;
  }

  if (cleanPath === "/email/manual-connect") {
    let email = "demo@nanvi.enterprise";
    let name = "Demo Email";
    try {
      if (init?.body) {
        const body = JSON.parse(init.body as string);
        if (body.email_address) email = body.email_address;
        if (body.display_name) name = body.display_name;
      }
    } catch {}
    return {
      status: "connected",
      account: {
        id: "email-demo-1",
        email_address: email,
        display_name: name,
        provider: "google",
        connected_at: new Date().toISOString(),
        is_active: true,
      },
    } as unknown as T;
  }

  if (cleanPath === "/settings/company-folder") {
    if (method === "PUT") {
      let reqPath = "C:\\CompanyData";
      try {
        if (init?.body) {
          const body = JSON.parse(init.body as string);
          if (body.path) reqPath = body.path;
        }
      } catch {}
      const res: CompanyFolderUpdateResponse = {
        status: "ok",
        path: reqPath,
        exists: true,
        folder_count: 5,
        file_count: 24,
        indexed_files: 24,
        message: "Company data directory updated and indexed successfully.",
      };
      return res as unknown as T;
    }

    const folderRes: CompanyFolderResponse = {
      path: "C:\\CompanyData",
      exists: true,
      folder_count: 5,
      file_count: 24,
    };
    return folderRes as unknown as T;
  }

  if (cleanPath === "/settings/company-folder/browse") {
    let reqPath = "C:\\CompanyData";
    try {
      if (init?.body) {
        const body = JSON.parse(init.body as string);
        if (body.path) reqPath = body.path;
      }
    } catch {}
    const browseRes: BrowseDirectoryResponse = {
      path: reqPath,
      parent: "C:\\",
      entries: [
        { name: "Contracts", path: `${reqPath}\\Contracts`, is_dir: true },
        { name: "Customers", path: `${reqPath}\\Customers`, is_dir: true },
        { name: "Finance", path: `${reqPath}\\Finance`, is_dir: true },
        { name: "HR", path: `${reqPath}\\HR`, is_dir: true },
        { name: "Operations", path: `${reqPath}\\Operations`, is_dir: true },
        { name: "Projects", path: `${reqPath}\\Projects`, is_dir: true },
      ],
    };
    return browseRes as unknown as T;
  }

  if (cleanPath === "/connections/categories") {
    return [
      "Communication",
      "Storage / Documents",
      "SQL Databases",
      "Developer Tools",
      "Cloud",
      "Vector / Search",
      "AI / LLM",
      "BI / Analytics",
      "Monitoring",
      "Identity",
    ] as unknown as T;
  }

  if (cleanPath === "/connections/providers") {
    const providersList: ProviderPublic[] = [
      {
        id: "google",
        name: "Google Workspace & Gmail",
        categories: ["Communication", "Identity"],
        icon: "google",
        description: "Connect enterprise Gmail mailboxes, Google Drive folders, and Google Workspace SSO.",
        auth_type: "oauth2",
        capabilities: ["read_email", "send_email", "search_drive"],
        available: true,
        available_reason: "ready",
        configuration_schema: {},
      },
      {
        id: "postgres",
        name: "PostgreSQL Database",
        categories: ["SQL Databases"],
        icon: "postgresql",
        description: "Connect enterprise relational PostgreSQL database with ACID transaction safety and SQL analytics.",
        auth_type: "db_password",
        capabilities: ["query", "schema", "table_read"],
        available: true,
        available_reason: "ready",
        configuration_schema: {
          properties: {
            host: { type: "string", title: "Host Server" },
            port: { type: "number", title: "Port", default: 5432 },
            database: { type: "string", title: "Database Name" },
            username: { type: "string", title: "Database User" },
            password: { type: "string", title: "Password", format: "password" },
          },
          required: ["host", "database", "username", "password"],
        },
      },
      {
        id: "github",
        name: "GitHub Repositories",
        categories: ["Developer Tools"],
        icon: "github",
        description: "Search enterprise repositories, analyze pull requests, and track code changes.",
        auth_type: "api_key",
        capabilities: ["read_repo", "code_search", "pull_requests"],
        available: true,
        available_reason: "ready",
        configuration_schema: {
          properties: {
            token: { type: "string", title: "Personal Access Token", format: "password" },
            organization: { type: "string", title: "GitHub Org / Owner" },
          },
          required: ["token"],
        },
      },
      {
        id: "supabase",
        name: "Supabase Cloud",
        categories: ["SQL Databases", "Cloud"],
        icon: "supabase",
        description: "Cloud PostgreSQL and pgvector database for real-time document search and vector indexing.",
        auth_type: "api_key",
        capabilities: ["vector_search", "sql_query"],
        available: true,
        available_reason: "ready",
        configuration_schema: {
          properties: {
            project_url: { type: "string", title: "Project URL" },
            api_key: { type: "string", title: "Service Role / API Key", format: "password" },
          },
          required: ["project_url", "api_key"],
        },
      },
      {
        id: "slack",
        name: "Slack Workspace",
        categories: ["Communication"],
        icon: "slack",
        description: "Index corporate communication channels, executive announcements, and project threads.",
        auth_type: "oauth2",
        capabilities: ["read_channels", "post_alerts"],
        available: true,
        available_reason: "ready",
        configuration_schema: {},
      },
      {
        id: "s3",
        name: "Amazon S3",
        categories: ["Storage / Documents", "Cloud"],
        icon: "aws",
        description: "Ingest PDFs, financial reports, and archives directly from AWS S3 buckets.",
        auth_type: "api_key",
        capabilities: ["read_objects", "bucket_sync"],
        available: true,
        available_reason: "ready",
        configuration_schema: {
          properties: {
            bucket: { type: "string", title: "Bucket Name" },
            region: { type: "string", title: "AWS Region", default: "us-east-1" },
            access_key_id: { type: "string", title: "Access Key ID" },
            secret_access_key: { type: "string", title: "Secret Access Key", format: "password" },
          },
          required: ["bucket", "access_key_id", "secret_access_key"],
        },
      },
      {
        id: "pinecone",
        name: "Pinecone Vector DB",
        categories: ["Vector / Search"],
        icon: "pinecone",
        description: "Serverless vector index for lightning-fast semantic retrieval and RAG indexing.",
        auth_type: "api_key",
        capabilities: ["vector_search", "upsert"],
        available: true,
        available_reason: "ready",
        configuration_schema: {
          properties: {
            api_key: { type: "string", title: "Pinecone API Key", format: "password" },
            index_name: { type: "string", title: "Index Name" },
            environment: { type: "string", title: "Environment Host" },
          },
          required: ["api_key", "index_name"],
        },
      },
      {
        id: "openai",
        name: "OpenAI Platform",
        categories: ["AI / LLM"],
        icon: "openai",
        description: "Connect enterprise OpenAI organization for GPT-4o, reasoning models, and embeddings.",
        auth_type: "api_key",
        capabilities: ["chat_completion", "text_embeddings"],
        available: true,
        available_reason: "ready",
        configuration_schema: {
          properties: {
            api_key: { type: "string", title: "API Key", format: "password" },
          },
          required: ["api_key"],
        },
      },
      {
        id: "microsoft365",
        name: "Microsoft 365 & Outlook",
        categories: ["Communication", "Identity"],
        icon: "microsoft365",
        description: "Integrate Outlook mailboxes, calendar events, and Office 365 documents.",
        auth_type: "oauth2",
        capabilities: ["read_mail", "read_calendar"],
        available: true,
        available_reason: "ready",
        configuration_schema: {},
      },
      {
        id: "jira",
        name: "Atlassian Jira",
        categories: ["Developer Tools"],
        icon: "jira",
        description: "Query enterprise project sprints, backlog tickets, and operational incidents.",
        auth_type: "oauth2",
        capabilities: ["read_issues", "search_projects"],
        available: true,
        available_reason: "ready",
        configuration_schema: {},
      },
    ];
    return { providers: providersList } as unknown as T;
  }

  if (cleanPath === "/connections/audit/events") {
    return [
      {
        id: "evt-1",
        event: "CONNECTION_CREATED",
        provider: "google",
        actor_user_id: "demo.executive@nanvi.enterprise",
        safe_metadata: { provider: "google", scope_level: "organization" },
        created_at: new Date(Date.now() - 86400000 * 2).toISOString(),
      },
      {
        id: "evt-2",
        event: "CONNECTION_TESTED",
        provider: "postgres",
        actor_user_id: "it.admin@nanvi.enterprise",
        safe_metadata: { status: "success", latency_ms: 18 },
        created_at: new Date(Date.now() - 3600000 * 5).toISOString(),
      },
      {
        id: "evt-3",
        event: "CONNECTION_OAUTH_CONNECTED",
        provider: "slack",
        actor_user_id: "demo.executive@nanvi.enterprise",
        safe_metadata: { workspace: "Nanvi HQ" },
        created_at: new Date(Date.now() - 3600000 * 2).toISOString(),
      },
    ] as unknown as T;
  }

  if (cleanPath.startsWith("/connections/oauth/") && cleanPath.endsWith("/authorize")) {
    const redirectParam = typeof window !== "undefined" ? window.location.origin : "";
    return {
      authorization_url: `${redirectParam}?connected=provider&status=success`,
    } as unknown as T;
  }

  if (cleanPath === "/connections/validate" || cleanPath.endsWith("/test")) {
    return {
      ok: true,
      message: "Connection verified successfully. Service responded in 24ms.",
    } as unknown as T;
  }

  if (cleanPath === "/connections") {
    if (method === "POST") {
      let bodyObj: any = {};
      try {
        if (init?.body) bodyObj = JSON.parse(init.body as string);
      } catch {}
      const newConn: ConnectionPublic = {
        id: `conn-demo-${Date.now()}`,
        provider: bodyObj.provider || "custom",
        display_name: bodyObj.display_name || "Custom Integration",
        account_identifier: bodyObj.account_identifier || "active-instance",
        scope_level: bodyObj.scope_level || "organization",
        status: "CONNECTED",
        status_reason: null,
        granted_scopes: ["read", "query"],
        metadata_safe: bodyObj.config || {},
        credential_type: "api_key",
        last_tested_at: new Date().toISOString(),
        last_used_at: new Date().toISOString(),
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        created_by: "Demo User",
        owner_user_id: "demo-user-1",
      };
      return newConn as unknown as T;
    }

    const connectionsList: ConnectionPublic[] = [
      {
        id: "conn-demo-google",
        provider: "google",
        display_name: "Google Workspace & Gmail",
        account_identifier: "executive@nanvi.enterprise",
        scope_level: "organization",
        status: "CONNECTED",
        status_reason: null,
        granted_scopes: ["email.readonly", "drive.readonly"],
        metadata_safe: { domain: "nanvi.enterprise", mode: "demo" },
        credential_type: "oauth2",
        last_tested_at: new Date(Date.now() - 3600000).toISOString(),
        last_used_at: new Date().toISOString(),
        last_synced_at: new Date().toISOString(),
        created_at: new Date(Date.now() - 86400000 * 7).toISOString(),
        updated_at: new Date().toISOString(),
        created_by: "System Administrator",
        owner_user_id: "demo-user-1",
      },
      {
        id: "conn-demo-postgres",
        provider: "postgres",
        display_name: "Enterprise Core DB",
        account_identifier: "db-primary.internal.nanvi:5432/core",
        scope_level: "organization",
        status: "CONNECTED",
        status_reason: null,
        granted_scopes: ["read_tables", "run_queries"],
        metadata_safe: { host: "db-primary.internal.nanvi", port: 5432, database: "core" },
        credential_type: "db_password",
        last_tested_at: new Date(Date.now() - 7200000).toISOString(),
        last_used_at: new Date().toISOString(),
        last_synced_at: new Date().toISOString(),
        created_at: new Date(Date.now() - 86400000 * 14).toISOString(),
        updated_at: new Date().toISOString(),
        created_by: "IT Admin",
        owner_user_id: "demo-admin-1",
      },
    ];

    return {
      connections: connectionsList,
      total: connectionsList.length,
    } as unknown as T;
  }

  if (cleanPath.startsWith("/connections/")) {
    if (method === "DELETE") {
      return {} as unknown as T;
    }
    if (method === "PATCH") {
      let bodyObj: any = {};
      try {
        if (init?.body) bodyObj = JSON.parse(init.body as string);
      } catch {}
      const updatedConn: ConnectionPublic = {
        id: cleanPath.split("/").pop() || "conn-demo",
        provider: "google",
        display_name: bodyObj.display_name || "Updated Connection",
        account_identifier: "executive@nanvi.enterprise",
        scope_level: "organization",
        status: "CONNECTED",
        status_reason: null,
        granted_scopes: ["read"],
        metadata_safe: {},
        credential_type: "oauth2",
        last_tested_at: new Date().toISOString(),
        created_at: new Date(Date.now() - 86400000).toISOString(),
        updated_at: new Date().toISOString(),
      };
      return updatedConn as unknown as T;
    }
  }

  if (cleanPath.startsWith("/sources/")) {
    const id = cleanPath.split("/").pop() || "doc-1";
    return {
      reference_id: id,
      source_type: "file",
      title: "Enterprise Strategy & Operations Briefing.pdf",
      snippet: "Nanvi Enterprise Assistant incorporates zero-trust role-based access control, cryptographic transparent citation traces, and multi-modal voice processing.",
      location: "CompanyData/Projects/Enterprise_Strategic_Plan_2026.pdf",
      page: 2,
    } as unknown as T;
  }

  if (cleanPath === "/documents/upload") {
    return {
      status: "ok",
      filename: "uploaded_doc.pdf",
      path: "CompanyData/uploaded_doc.pdf",
      size_bytes: 2048,
      message: "Document indexed and secured successfully.",
    } as unknown as T;
  }

  if (cleanPath.startsWith("/reports/") && cleanPath.endsWith("/download")) {
    const downloadUrl = typeof window !== "undefined" ? window.location.origin : "#";
    return { download_url: downloadUrl } as unknown as T;
  }

  if (cleanPath === "/chat") {
    let query = "Hello";
    let conversationId = `conv-${Date.now()}`;
    try {
      if (init?.body) {
        const parsed = JSON.parse(init.body as string);
        if (parsed.query) query = parsed.query;
        if (parsed.conversation_id) conversationId = parsed.conversation_id;
      }
    } catch {
      // Keep default query
    }

    const demoAnswer = `### Nanvi AI Enterprise Intelligence\n\nI have received your inquiry: **"${query}"**.\n\nYou are viewing the live **Cloud Demo** of Nanvi AI.\n\n* **Role-Based Access Control (RBAC):** Your user role permissions are actively enforced.\n* **RAG Pipeline:** When paired with the Python backend via \`VITE_API_BASE_URL\`, queries cross-reference documents (PDFs, Excel, Word), mailboxes, and SQL tables with zero data exfiltration.\n* **Source Grounding:** Every insight includes cryptographic transparency references to the underlying enterprise documents.`;

    const chatRes: ChatResponse = {
      conversation_id: conversationId,
      answer: demoAnswer,
      capability: "knowledge",
      sources: [
        {
          reference_id: "demo-doc-1",
          source_type: "file",
          display_name: "Enterprise_Strategic_Plan_2026.pdf",
          title: "Enterprise Strategy & Operations",
          location: "CompanyData/Projects/Enterprise_Strategic_Plan_2026.pdf",
          page: 2,
        },
        {
          reference_id: "demo-email-1",
          source_type: "email",
          display_name: "Executive Briefing: Q3 Performance",
          title: "Operations & Leadership Sync",
          timestamp: new Date().toISOString(),
        },
      ],
      trace: [
        "Verified Zero-Trust RBAC user role permissions",
        "Discovered 2 authorized reference sources matching query context",
        "Synthesized answer with citation guarantees",
      ],
      history: [
        { role: "user", content: query, created_at: new Date().toISOString() },
        { role: "assistant", content: demoAnswer, created_at: new Date().toISOString() },
      ],
    };
    return chatRes as unknown as T;
  }

  if (cleanPath === "/voice/transcribe") {
    return {
      text: "How are our quarterly milestones performing?",
      confidence: 0.98,
    } as unknown as T;
  }

  if (cleanPath === "/voice/respond") {
    let query = "Voice assistant active";
    let conversationId = `conv-${Date.now()}`;
    try {
      if (init?.body) {
        const parsed = JSON.parse(init.body as string);
        if (parsed.query) query = parsed.query;
        if (parsed.conversation_id) conversationId = parsed.conversation_id;
      }
    } catch {
      // Keep default
    }

    const spokenText = "Welcome to Nanvi Enterprise Assistant. Voice mode is active and listening.";
    const voiceRes: VoiceResponse = {
      conversation_id: conversationId,
      answer: `Voice session activated. Processed query: "${query}".`,
      spoken_text: spokenText,
      important_points: ["Voice mode connected", "Zero-trust session established", "Ready for voice input"],
      capability: "voice",
      sources: [],
      trace: ["Audio input processed", "Neural core responded"],
      history: [
        { role: "user", content: query, created_at: new Date().toISOString() },
        { role: "assistant", content: spokenText, created_at: new Date().toISOString() },
      ],
    };
    return voiceRes as unknown as T;
  }

  return undefined;
}
