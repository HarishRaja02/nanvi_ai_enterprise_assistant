import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { RoleLoginForm } from "./RoleLoginForm";

describe("RoleLoginForm", () => {
  it("shows roles only after clicking the dropdown button, and submits with the selected role", async () => {
    const user = userEvent.setup();
    const onLogin = vi.fn().mockResolvedValue(undefined);
    render(<RoleLoginForm onLogin={onLogin} loading={false} error="" />);

    expect(screen.getByRole("heading", { name: "Sign in to Nanvi" })).toBeInTheDocument();

    // Roles are hidden by default until the dropdown button is clicked
    expect(screen.queryByRole("button", { name: /Supervisor/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Project Engineer/i })).not.toBeInTheDocument();

    // Click the dropdown button to reveal roles
    const dropdownBtn = screen.getByRole("button", { name: /Superior/i });
    expect(dropdownBtn).toHaveAttribute("aria-expanded", "false");
    await user.click(dropdownBtn);

    // Roles are now visible in the dropdown
    expect(screen.getByRole("button", { name: /Supervisor/i })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: /Project Engineer/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Employee/i })).toBeInTheDocument();

    // Try submitting without credentials -> validation error
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/password/i);
    expect(onLogin).not.toHaveBeenCalled();

    // Re-open dropdown if it was closed or select Project Engineer
    if (!screen.queryByRole("button", { name: /Project Engineer/i })) {
      await user.click(screen.getByRole("button", { name: /Superior/i }));
    }
    await user.click(screen.getByRole("button", { name: /Project Engineer/i }));

    // Selected role button now reflects Project Engineer
    expect(screen.getByRole("button", { name: /Project Engineer/i })).toBeInTheDocument();

    await user.type(screen.getByLabelText(/Email ID or User ID/i), "maya");
    await user.type(screen.getByLabelText("Password"), "a-strong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(onLogin).toHaveBeenCalledWith("maya", "a-strong-password", "Project Engineer");
  });
});