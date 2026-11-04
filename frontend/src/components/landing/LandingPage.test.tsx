import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LandingPage } from "./LandingPage";

describe("LandingPage", () => {
  it("renders the enterprise value proposition, hero title, and download buttons", () => {
    render(<LandingPage onLaunchWebApp={vi.fn()} />);

    // Title & Brand
    expect(screen.getByRole("heading", { level: 1, name: /The Secure Enterprise AI Assistant/i })).toBeInTheDocument();

    // Primary Action Buttons
    expect(screen.getAllByText(/Download for Windows/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Launch Web Assistant/i).length).toBeGreaterThan(0);

    // Capabilities Section
    expect(screen.getByText(/What Nanvi AI Does & What You Use It For/i)).toBeInTheDocument();
    expect(screen.getByText(/Invoice & Ledger Auditing/i)).toBeInTheDocument();
    expect(screen.getByText(/Private Local PC Indexing/i)).toBeInTheDocument();

    // Dual Architecture Section
    expect(screen.getByText(/Both Web Service & Local Application/i)).toBeInTheDocument();
    expect(screen.getByText(/Local Windows Application/i)).toBeInTheDocument();
    expect(screen.getByText(/Enterprise Cloud Web Portal/i)).toBeInTheDocument();
  });

  it("calls onLaunchWebApp when the user clicks Launch Web Assistant", async () => {
    const user = userEvent.setup();
    const mockLaunch = vi.fn();

    render(<LandingPage onLaunchWebApp={mockLaunch} />);

    const launchBtns = screen.getAllByRole("button", { name: /Launch Web Assistant/i });
    expect(launchBtns.length).toBeGreaterThan(0);

    await user.click(launchBtns[0]);
    expect(mockLaunch).toHaveBeenCalled();
  });

  it("allows switching sample enterprise queries in the interactive mockup", async () => {
    const user = userEvent.setup();
    render(<LandingPage onLaunchWebApp={vi.fn()} />);

    // Initially on "Vendor Invoice Search"
    expect(screen.getByText("invoice_register.csv")).toBeInTheDocument();

    // Click "Payment Aging Audit" pill
    const agingPill = screen.getByRole("button", { name: /Payment Aging Audit/i });
    await user.click(agingPill);

    // Shows updated mockup file
    expect(screen.getByText("invoice_aging.xlsx")).toBeInTheDocument();
  });
});

