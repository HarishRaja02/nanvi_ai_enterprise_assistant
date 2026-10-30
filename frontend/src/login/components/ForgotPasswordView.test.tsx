import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ForgotPasswordView } from "./ForgotPasswordView";
import { api } from "../../api";

describe("ForgotPasswordView", () => {
  it("submits username and email and displays inbox confirmation", async () => {
    const user = userEvent.setup();
    const onBackToSignIn = vi.fn();
    const onOpenResetLink = vi.fn();

    vi.spyOn(api, "forgotPassword").mockResolvedValueOnce({
      status: "ok",
      message: "Recovery link dispatched.",
      dev_reset_link: "http://localhost:5173/?token=test-token-123",
    });

    render(
      <ForgotPasswordView
        onBackToSignIn={onBackToSignIn}
        onOpenResetLink={onOpenResetLink}
      />
    );

    expect(screen.getByRole("heading", { name: "Reset Password" })).toBeInTheDocument();

    await user.type(screen.getByLabelText(/Enterprise User ID/i), "maya.nair");
    await user.type(screen.getByLabelText(/Registered Email Address/i), "maya.nair@company.com");
    await user.click(screen.getByRole("button", { name: "Send Recovery Link" }));

    expect(api.forgotPassword).toHaveBeenCalledWith("maya.nair", "maya.nair@company.com");
    expect(await screen.findByText("Check Your Inbox")).toBeInTheDocument();
    expect(screen.getByText("maya.nair@company.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Open Reset Link/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Open Reset Link/i }));
    expect(onOpenResetLink).toHaveBeenCalledWith("test-token-123");
  });
});
