export const TOKEN_KEY = "nanvi_access_token";

export function getStoredToken(): string | null { return sessionStorage.getItem(TOKEN_KEY); }
export function setStoredToken(token: string) { sessionStorage.setItem(TOKEN_KEY, token); }
export function clearStoredToken() { sessionStorage.removeItem(TOKEN_KEY); }
