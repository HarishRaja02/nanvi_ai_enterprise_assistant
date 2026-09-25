import { DEMO_MODE } from "./config";
import type { ChatResponse, VoiceResponse } from "../api";

export function getDemoFallbackResponse<T>(path: string, init?: RequestInit): T | undefined {
  if (!DEMO_MODE) return undefined;

  const cleanPath = path.split("?")[0].replace(/\/$/, "");

  if (cleanPath === "/chat/history") {
    return { conversations: [] } as unknown as T;
  }

  if (cleanPath === "/email/status") {
    return {
      connected: false,
      email: null,
      total_messages: 0,
      provider: "google",
      accounts: [],
    } as unknown as T;
  }

  if (cleanPath === "/settings/company-folder") {
    return {
      configured: true,
      active_folder: "C:\\CompanyData",
      allowed_roles: ["CEO", "Manager", "Finance", "HR", "Employee", "IT_Admin"],
      sample_folders: ["Contracts", "Customers", "Finance", "HR", "Projects"],
    } as unknown as T;
  }

  if (cleanPath === "/connections/categories") {
    return ["database", "cloud_storage", "code_repository", "productivity", "custom_api"] as unknown as T;
  }

  if (cleanPath === "/connections/providers") {
    return {
      providers: [
        { provider_type: "postgres", display_name: "PostgreSQL Database", category: "database", auth_type: "basic" },
        { provider_type: "supabase", display_name: "Supabase Cloud", category: "database", auth_type: "api_key" },
        { provider_type: "google", display_name: "Google Workspace / Gmail", category: "productivity", auth_type: "oauth2" },
        { provider_type: "github", display_name: "GitHub Repositories", category: "code_repository", auth_type: "token" },
      ],
    } as unknown as T;
  }

  if (cleanPath === "/connections") {
    return { connections: [], total: 0 } as unknown as T;
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
