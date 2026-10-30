import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { RoleLoginForm } from "./RoleLoginForm";

describe("RoleLoginForm", () => {
  it("requires credentials and submits the selected role with the account", async () => {
    const user = userEvent.setup();
    const onLogin = vi.fn().mockResolvedValue(undefined);
    render(<RoleLoginForm onLogin={onLogin} loading={false} error="" />);

    expect(screen.getByRole("heading", { name: "Sign in to Nanvi" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Superior/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /Supervisor/i })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: /Project Engineer/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Employee/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/password/i);
    expect(onLogin).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /Project Engineer/i }));
    expect(screen.getByRole("button", { name: /Project Engineer/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /Superior/i })).toHaveAttribute("aria-pressed", "false");

    await user.type(screen.getByLabelText(/Email ID or User ID/i), "maya");
    await user.type(screen.getByLabelText("Password"), "a-strong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(onLogin).toHaveBeenCalledWith("maya", "a-strong-password", "Project Engineer");
  });
});