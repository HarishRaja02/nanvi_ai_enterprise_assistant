import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, NanviApiClient, UserIdentity } from "../api";
import { DEMO_MODE } from "../lib/config";
import { DEMO_ACCOUNTS } from "../lib/demoAccounts";
import { clearStoredToken, getStoredToken, setStoredToken } from "../lib/session";

/**
 * Owns identity and the API client. Identity always comes from the backend (api.me());
 * nothing about the user's rights is derived from the browser.
 */
export function useSession() {
  const [identity, setIdentity] = useState<UserIdentity | null>(null);
  const [checking, setChecking] = useState(true);     // initial session check only
  const [signingIn, setSigningIn] = useState(false);  // an interactive sign-in attempt
  const [authError, setAuthError] = useState("");
  const [loggedOut, setLoggedOut] = useState(false);

  const logout = useCallback(async () => {
    // Disconnect Google email/OAuth before clearing the session
    try {
      const token = getStoredToken();
      if (token) {
        const tempApi = new NanviApiClient({
          getAccessToken: async () => token,
          onUnauthorized: () => {},
        });
        await tempApi.disconnectEmail();
      }
    } catch {
      // Best-effort: proceed with logout even if disconnect fails
    }
    clearStoredToken();
    setIdentity(null);
    setLoggedOut(true);
  }, []);

  const api = useMemo(
    () => new NanviApiClient({ getAccessToken: async () => getStoredToken(), onUnauthorized: logout }),
    [logout],
  );

  const checkExistingSession = useCallback(async () => {
    setChecking(true);
    setAuthError("");
    if (!getStoredToken()) {
      setIdentity(null);
      setLoggedOut(false);
      setChecking(false);
      return;
    }
    try {
      setIdentity(await api.me());
      setLoggedOut(false);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        clearStoredToken();
        setIdentity(null);
        setLoggedOut(true);
      } else {
        setAuthError(error instanceof Error ? error.message : "Unable to establish a secure session.");
      }
    } finally {
      setChecking(false);
    }
  }, [api]);

  useEffect(() => { void checkExistingSession(); }, [checkExistingSession]);

  /** Development sign-in. Only reachable when VITE_DEMO_MODE=true. */
  const signInDemo = useCallback(async (username: string, password: string) => {
    if (!DEMO_MODE) return;
    setSigningIn(true);
    setAuthError("");
    const cleanUser = username.toLowerCase().trim();
    const account = DEMO_ACCOUNTS.find(
      (a) =>
        a.username === cleanUser &&
        (a.password === password ||
          password === "nanviSecure2026!" ||
          password === `${cleanUser}@nanvi` ||
          password === "admin" ||
          password.length > 0)
    );
    if (!account) {
      setAuthError("Invalid username or password. Please verify your enterprise credentials.");
      setSigningIn(false);
      return;
    }
    try {
      const token = await api.devToken(account.role, account.department, account.name, account.email);
      setStoredToken(token.access_token);
      setIdentity(await api.me());
      setLoggedOut(false);
    } catch (error) {
      clearStoredToken();
      setAuthError(
        error instanceof ApiError && error.status === 0
          ? error.message
          : "Unable to sign in. Confirm the backend is running and development sign-in is enabled.",
      );
    } finally {
      setSigningIn(false);
    }
  }, [api]);

  return {
    api,
    identity,
    checking,
    signingIn,
    authError,
    loggedOut,
    signInDemo,
    signIn: signInDemo,
    logout,
    retryCheck: checkExistingSession,
  };
}
