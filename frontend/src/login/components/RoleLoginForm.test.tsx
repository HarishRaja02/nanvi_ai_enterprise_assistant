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
    expect(screen.getByRole("combobox", { name: "Role" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter your User ID and password.");
    expect(onLogin).not.toHaveBeenCalled();

    await user.selectOptions(screen.getByRole("combobox", { name: "Role" }), "Project Engineer");
    await user.type(screen.getByRole("textbox", { name: "User ID" }), "maya");
    await user.type(screen.getByLabelText("Password"), "a-strong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(onLogin).toHaveBeenCalledWith("maya", "a-strong-password", "Project Engineer");
  });
});