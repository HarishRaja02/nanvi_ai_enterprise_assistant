import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ResetPasswordView } from "./ResetPasswordView";
import { api } from "../../api";

describe("ResetPasswordView", () => {
  it("verifies token on load and updates password successfully", async () => {
    const user = userEvent.setup();
    const onBackToSignIn = vi.fn();

    vi.spyOn(api, "verifyResetToken").mockResolvedValueOnce({
      valid: true,
      username: "maya.nair",
      email: "maya.nair@company.com",
      display_name: "Maya Nair",
    });

    vi.spyOn(api, "resetPasswordWithToken").mockResolvedValueOnce({
      status: "ok",
      message: "Password updated successfully.",
    });

    render(
      <ResetPasswordView
        token="valid-test-token"
        onBackToSignIn={onBackToSignIn}
      />
    );

    expect(await screen.findByRole("heading", { name: "Create New Password" })).toBeInTheDocument();
    expect(screen.getByText("maya.nair")).toBeInTheDocument();

    await user.type(screen.getByLabelText(/^New Password$/i), "NewSecret2026!");
    await user.type(screen.getByLabelText(/^Confirm New Password$/i), "NewSecret2026!");
    await user.click(screen.getByRole("button", { name: "Update Password" }));

    expect(api.resetPasswordWithToken).toHaveBeenCalledWith("valid-test-token", "NewSecret2026!");
    expect(await screen.findByText("Password Successfully Updated")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Sign In with New Password" }));
    expect(onBackToSignIn).toHaveBeenCalled();
  });

  it("handles invalid or expired tokens gracefully", async () => {
    const onBackToSignIn = vi.fn();
    const onRequestNewLink = vi.fn();

    vi.spyOn(api, "verifyResetToken").mockRejectedValueOnce(
      new Error("The password reset link is invalid or has expired.")
    );

    render(
      <ResetPasswordView
        token="expired-token"
        onBackToSignIn={onBackToSignIn}
        onRequestNewLink={onRequestNewLink}
      />
    );

    expect(await screen.findByText("Invalid or Expired Link")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Request New Recovery Link" })).toBeInTheDocument();
  });
});
