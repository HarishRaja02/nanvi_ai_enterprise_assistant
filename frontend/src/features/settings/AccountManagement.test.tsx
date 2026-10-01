import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { NanviApiClient, UserIdentity } from "../../api";
import { AccountManagement } from "./AccountManagement";

const supervisor: UserIdentity = {
  subject: "supervisor-1",
  issuer: "nanvi-local",
  roles: ["Supervisor"],
  tenant_id: "tenant-1",
};

describe("AccountManagement", () => {
  it("limits Supervisor account creation and removal to Project Engineer and Employee", async () => {
    const user = userEvent.setup();
    const createLocalAccount = vi.fn().mockResolvedValue({});
    const deleteLocalAccount = vi.fn().mockResolvedValue(undefined);
    const listLocalAccounts = vi.fn().mockResolvedValue([{
      id: "employee-1",
      username: "employee.one",
      role: "Employee",
      display_name: "Employee One",
      department: "Operations",
      active: true,
    }]);
    const api = { createLocalAccount, deleteLocalAccount, listLocalAccounts } as unknown as NanviApiClient;
    render(<AccountManagement api={api} identity={supervisor} />);

    const roleSelect = screen.getByRole("combobox", { name: "Role" });
    expect(roleSelect.querySelectorAll("option")).toHaveLength(2);
    expect(screen.queryByRole("option", { name: "Superior" })).not.toBeInTheDocument();

    await user.type(screen.getByRole("textbox", { name: "User ID" }), "project.eng");
    await user.type(screen.getByRole("textbox", { name: "Name" }), "Project Engineer");
    await user.type(screen.getByLabelText("Temporary password"), "secure-project-password");
    await user.selectOptions(roleSelect, "Project Engineer");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => expect(createLocalAccount).toHaveBeenCalledWith(expect.objectContaining({
      username: "project.eng",
      role: "Project Engineer",
      display_name: "Project Engineer",
    })));

    await screen.findByText("Employee One");
    await user.click(screen.getByRole("button", { name: "Remove employee.one" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(deleteLocalAccount).toHaveBeenCalledWith("employee-1"));
  });
});