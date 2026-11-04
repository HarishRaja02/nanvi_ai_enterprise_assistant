import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, NanviApiClient, UserIdentity } from "../api";
import type { LocalAccountRole } from "../api";
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

  const logout = useCallback(async (reason?: string) => {
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
    if (reason) {
      setAuthError(reason);
    }
  }, []);

  const api = useMemo(
    () => new NanviApiClient({
      getAccessToken: async () => getStoredToken(),
      onUnauthorized: () => void logout("Your session has expired or your account access was modified."),
    }),
    [logout],
  );

  const checkExistingSession = useCallback(async () => {
    setChecking(true);
    setAuthError("");
    const storedToken = getStoredToken();
    if (!storedToken) {
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
        setAuthError("Your account has been deactivated or session has expired.");
      } else {
        setAuthError(error instanceof Error ? error.message : "Unable to establish a secure session.");
      }
    } finally {
      setChecking(false);
    }
  }, [api]);

  useEffect(() => { void checkExistingSession(); }, [checkExistingSession]);

  // Periodic heartbeat to instantly detect when an administrator deactivates or blocks the user from the Web Admin Dashboard
  useEffect(() => {
    if (!identity) return;
    const interval = setInterval(async () => {
      try {
        await api.me();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          void logout("Your account has been deactivated by the system administrator.");
        }
      }
    }, 30000);

    return () => clearInterval(interval);
  }, [identity, api, logout]);

  const signInLocal = useCallback(async (username: string, password: string, role?: LocalAccountRole | string) => {
    setSigningIn(true);
    setAuthError("");
    try {
      clearStoredToken();
      const token = await api.localLogin(username, password, role);
      setStoredToken(token.access_token);
      setIdentity(await api.me());
      setLoggedOut(false);
    } catch (error) {
      clearStoredToken();
      setAuthError(error instanceof ApiError ? error.message : "Unable to sign in. Check your User ID, password, and role.");
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
    signIn: signInLocal,
    logout,
    retryCheck: checkExistingSession,
  };
}
