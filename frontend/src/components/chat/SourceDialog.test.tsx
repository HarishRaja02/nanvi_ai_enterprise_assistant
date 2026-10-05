import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SourceDialog } from "./SourceDialog";
import type { SourceView } from "../../lib/sources";
import type { NanviApiClient } from "../../api";

describe("SourceDialog", () => {
  const mockSource: SourceView = {
    id: "web-test-1",
    kind: "web",
    format: "WEB",
    title: "Is India's finance boom outrunning its real economy?",
    location: "https://example.com/finance-boom",
    href: "https://example.com/finance-boom",
    snippet: "India's financial sector has grown rapidly, exceeding real economy pace.",
  };

  it("immediately renders the source title, details, and content excerpt without blocking", () => {
    const mockApi = {
      source: vi.fn().mockReturnValue(new Promise(() => {})), // Never resolves (simulates slow network)
    } as unknown as NanviApiClient;

    render(<SourceDialog source={mockSource} api={mockApi} onClose={vi.fn()} />);

    // Title must be visible immediately
    expect(screen.getByText("Is India's finance boom outrunning its real economy?")).toBeInTheDocument();

    // Content excerpt must be visible immediately
    expect(screen.getByText(/India's financial sector has grown rapidly/)).toBeInTheDocument();

    // Location / link must be visible immediately
    expect(screen.getByText("https://example.com/finance-boom")).toBeInTheDocument();

    // Verification in progress badge
    expect(screen.getByText(/Confirming server access/)).toBeInTheDocument();
  });

  it("updates to access confirmed when the server verifies the source", async () => {
    const mockApi = {
      source: vi.fn().mockResolvedValue({
        reference_id: "web-test-1",
        source_type: "website",
        display_name: "Is India's finance boom outrunning its real economy?",
        title: "Is India's finance boom outrunning its real economy?",
        location: "https://example.com/finance-boom",
        href: "https://example.com/finance-boom",
        snippet: "Verified content snippet from server",
      }),
    } as unknown as NanviApiClient;

    render(<SourceDialog source={mockSource} api={mockApi} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("Access confirmed")).toBeInTheDocument();
    });

    expect(screen.getByText("Verified content snippet from server")).toBeInTheDocument();
  });

  it("displays copy buttons and allows copying excerpt", async () => {
    const user = userEvent.setup();
    const mockApi = {
      source: vi.fn().mockResolvedValue({
        reference_id: "web-test-1",
        source_type: "website",
        display_name: "Source",
      }),
    } as unknown as NanviApiClient;

    render(<SourceDialog source={mockSource} api={mockApi} onClose={vi.fn()} />);

    const copyBtn = screen.getByTitle("Copy excerpt text");
    expect(copyBtn).toBeInTheDocument();
    await user.click(copyBtn);

    const copyDetailsBtn = screen.getByRole("button", { name: /Copy details/i });
    expect(copyDetailsBtn).toBeInTheDocument();
  });
});
