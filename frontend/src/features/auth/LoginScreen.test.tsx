import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

async function loadLogin(env: Record<string, string>) {
  vi.resetModules();
  for (const [k, v] of Object.entries(env)) vi.stubEnv(k, v);
  return (await import("./LoginScreen")).LoginScreen;
}
const props = { error: "", loggedOut: false, signingIn: false, onDemoSignIn: vi.fn().mockResolvedValue(undefined) };

afterEach(() => { vi.unstubAllEnvs(); vi.clearAllMocks(); });

describe("LoginScreen", () => {
  it("demo mode: validates on submit with inline, associated errors", async () => {
    const Login = await loadLogin({ VITE_DEMO_MODE: "true" });
    const user = userEvent.setup();
    render(<Login {...props} />);
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.getByText("Enter your username.")).toBeInTheDocument();
    expect(screen.getByLabelText(/Username/)).toHaveAttribute("aria-invalid", "true");
    expect(props.onDemoSignIn).not.toHaveBeenCalled();
  });

  it("demo mode: signs in with entered credentials", async () => {
    const Login = await loadLogin({ VITE_DEMO_MODE: "true" });
    const user = userEvent.setup();
    render(<Login {...props} />);
    await user.type(screen.getByLabelText(/Username/), "ceo");
    await user.type(screen.getByLabelText(/Password/), "pw");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(props.onDemoSignIn).toHaveBeenCalledWith("ceo", "pw");
  });

  it("production: no credential form, no demo accounts, no dev-login UI", async () => {
    const Login = await loadLogin({ VITE_DEMO_MODE: "false", VITE_SSO_LOGIN_URL: "" });
    render(<Login {...props} />);
    expect(screen.queryByLabelText(/Password/)).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Demo accounts" })).not.toBeInTheDocument();
    expect(screen.getByText("Single sign-on isn't set up")).toBeInTheDocument();
  });

  it("production: offers SSO when a valid URL is configured, and ignores an unsafe one", async () => {
    let Login = await loadLogin({ VITE_DEMO_MODE: "false", VITE_SSO_LOGIN_URL: "https://sso.example.com/authorize" });
    const { unmount } = render(<Login {...props} />);
    expect(screen.getByRole("button", { name: /Sign in with company SSO/ })).toBeInTheDocument();
    unmount();
    Login = await loadLogin({ VITE_DEMO_MODE: "false", VITE_SSO_LOGIN_URL: "javascript:alert(1)" });
    render(<Login {...props} />);
    expect(screen.queryByRole("button", { name: /company SSO/ })).not.toBeInTheDocument();
  });

  it("announces errors", async () => {
    const Login = await loadLogin({ VITE_DEMO_MODE: "false" });
    render(<Login {...props} error="Nanvi is unreachable." />);
    expect(screen.getByRole("alert")).toHaveTextContent("Nanvi is unreachable.");
  });
});
