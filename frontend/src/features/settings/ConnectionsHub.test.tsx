import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { NanviApiClient, ProviderPublic } from "../../api";
import { ConnectionsHub } from "./ConnectionsHub";

const provider = (overrides: Partial<ProviderPublic>): ProviderPublic => ({
  id: "ready-provider",
  name: "Ready Provider",
  categories: ["Cloud"],
  icon: "plug",
  description: "A configured provider.",
  auth_type: "api_key",
  capabilities: [],
  available: true,
  available_reason: "available",
  configuration_schema: {},
  ...overrides,
});

describe("ConnectionsHub provider catalog", () => {
  it("hides coming-soon cards without hiding available providers", async () => {
    const api = {
      listProviders: vi.fn().mockResolvedValue({
        providers: [
          provider({ id: "google-drive", name: "Google Drive" }),
          provider({ id: "datadog", name: "Datadog", available: false, available_reason: "coming_soon" }),
        ],
      }),
      listConnectionCategories: vi.fn().mockResolvedValue(["Cloud"]),
      listConnections: vi.fn().mockResolvedValue({ connections: [] }),
    } as unknown as NanviApiClient;

    render(<ConnectionsHub api={api} canManageOrg={false} />);

    await waitFor(() => expect(screen.getByRole("heading", { name: "Integrations Catalog (1)" })).toBeInTheDocument());
    expect(screen.getByText("Google Drive")).toBeInTheDocument();
    expect(screen.queryByText("Datadog")).not.toBeInTheDocument();
    expect(screen.queryByText("Coming soon")).not.toBeInTheDocument();
  });
});