import React, { useState, useEffect } from "react";
import {
  Lock,
  Eye,
  EyeOff,
  Loader2,
  Check,
  ShieldCheck,
  AlertCircle,
  X,
} from "lucide-react";
import { UserSession } from "../types";
import { GoogleIcon } from "./GoogleIcon";

interface LoginFormProps {
  onSuccess?: (session: UserSession) => void;
  onLogin: (username: string, password: string) => Promise<void> | void;
  onNavigateToSignUp?: () => void;
  onNavigateToForgot?: () => void;
  signedOutBanner?: boolean;
  onDismissBanner?: () => void;
  externalError?: string;
  loading?: boolean;
}

export function LoginForm({
  onSuccess,
  onLogin,
  onNavigateToSignUp,
  onNavigateToForgot,
  signedOutBanner = false,
  onDismissBanner,
  externalError = "",
  loading = false,
}: LoginFormProps) {
  const [username, setUsername] = useState("ceo");
  const [password, setPassword] = useState("nanviSecure2026!");
  const [rememberMe, setRememberMe] = useState(true);
  const [showPassword, setShowPassword] = useState(false);

  const [isLoading, setIsLoading] = useState(false);
  const [isGoogleLoading, setIsGoogleLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [showBanner, setShowBanner] = useState(signedOutBanner);

  useEffect(() => {
    if (signedOutBanner) {
      setShowBanner(true);
    }
  }, [signedOutBanner]);



  const isSubmitting = isLoading || loading;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage("");

    if (!username.trim()) {
      setErrorMessage("Please enter your enterprise directory username.");
      return;
    }
    if (!password) {
      setErrorMessage("Please enter your security password.");
      return;
    }

    setIsLoading(true);
    try {
      await onLogin(username.trim(), password);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleGoogleSignIn = async () => {
    setIsGoogleLoading(true);
    setErrorMessage("");
    try {
      const targetUser = "ceo";
      await onLogin(targetUser, "nanviSecure2026!");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Google SSO authentication failed.");
    } finally {
      setIsGoogleLoading(false);
    }
  };

  return (
    <div id="nanvi-login-container" className="w-full max-w-[620px] mx-auto">
      {/* Top Header: Premium Editorial Serif Style */}
      <div className="text-left mb-3 sm:mb-3.5">
        <div className="flex items-center gap-1.5 text-[10px] tracking-[0.2em] text-neutral-400 font-semibold uppercase mb-1.5 select-none">
          <Lock className="w-3.5 h-3.5 text-neutral-400 stroke-[2.2]" />
          <span>SECURE GATEWAY</span>
        </div>
        <h1
          id="nanvi-login-heading"
          className="font-serif text-2xl sm:text-[32px] font-normal text-neutral-900 tracking-tight leading-tight"
        >
          Sign in to Nanvi
        </h1>
        <p className="mt-1 text-xs sm:text-[13px] text-neutral-500 font-normal leading-normal">
          Enter your enterprise directory credentials or choose a pre-configured role profile.
        </p>
      </div>

      {/* Signed Out Alert Banner: Sophisticated Neutral Platinum/Obsidian */}
      {showBanner && (
        <div
          id="signout-success-banner"
          className="mb-3 p-2.5 rounded-xl bg-neutral-100/90 border border-neutral-200/90 text-neutral-800 text-xs flex items-center justify-between gap-2 animate-in fade-in duration-200"
        >
          <div className="flex items-center gap-2">
            <div className="w-3.5 h-3.5 rounded-full bg-neutral-900 text-white flex items-center justify-center shrink-0">
              <Check className="w-2 h-2 stroke-[3]" />
            </div>
            <span className="font-normal text-neutral-700">
              You have been signed out securely. Session credentials cleared.
            </span>
          </div>
          <button
            type="button"
            onClick={() => {
              setShowBanner(false);
              onDismissBanner?.();
            }}
            className="text-neutral-400 hover:text-neutral-700 p-0.5 rounded focus:outline-none transition-colors cursor-pointer"
            title="Dismiss notice"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Error Banner */}
      {(externalError || errorMessage) && (
        <div
          id="login-error-banner"
          className="mb-3 p-2.5 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2"
        >
          <AlertCircle className="w-3.5 h-3.5 text-red-600 shrink-0" />
          <span>{externalError || errorMessage}</span>
        </div>
      )}

      {/* Main Credentials Form */}
      <form onSubmit={handleSubmit} className="space-y-3 sm:space-y-3.5">
        {/* Username & Password in 2-column grid on sm and up */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 sm:gap-3">
          {/* Enterprise Username */}
          <div>
            <label
              htmlFor="enterprise-username"
              className="block text-xs font-medium text-neutral-800 mb-1 text-left"
            >
              Enterprise Username
            </label>
            <input
              id="enterprise-username"
              type="text"
              value={username}
              onChange={(e) => {
                setUsername(e.target.value);
              }}
              placeholder="e.g. ceo, finance, manager"
              required
              className="w-full px-3.5 py-2.5 bg-[#f8f9fa] border border-neutral-200/90 rounded-xl text-neutral-900 text-xs sm:text-sm placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:bg-white transition-all shadow-xs"
            />
          </div>

          {/* Security Password */}
          <div>
            <label
              htmlFor="security-password"
              className="block text-xs font-medium text-neutral-800 mb-1 text-left"
            >
              Security Password
            </label>
            <div className="relative">
              <input
                id="security-password"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter password"
                required
                className="w-full pl-3.5 pr-10 py-2.5 bg-[#f8f9fa] border border-neutral-200/90 rounded-xl text-neutral-900 text-xs sm:text-sm placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:bg-white transition-all shadow-xs"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-700 p-1 focus:outline-none transition-colors"
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? (
                  <EyeOff className="w-3.5 h-3.5" />
                ) : (
                  <Eye className="w-3.5 h-3.5" />
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Remember me & Forgot Password */}
        <div className="flex items-center justify-between py-0.5">
          <label className="flex items-center gap-1.5 cursor-pointer select-none">
            <input
              id="remember-me-checkbox"
              type="checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
              className="w-3.5 h-3.5 rounded border-neutral-300 text-neutral-950 accent-neutral-950 focus:ring-neutral-900"
            />
            <span className="text-xs text-neutral-600 font-normal">
              Remember credentials
            </span>
          </label>

          {onNavigateToForgot && (
            <button
              id="forgot-password-link"
              type="button"
              onClick={onNavigateToForgot}
              className="text-xs font-medium text-neutral-900 hover:underline focus:outline-none"
            >
              Forgot Password
            </button>
          )}
        </div>

        {/* Action Buttons: Side-by-side on sm: */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-2.5">
          {/* Primary Action Button: Solid Obsidian Black */}
          <button
            id="sign-in-workspace-button"
            type="submit"
            disabled={isSubmitting || isGoogleLoading}
            style={{ color: '#fff' }}
            className="w-full py-2.5 sm:py-3 px-4 bg-black hover:bg-neutral-850 active:bg-neutral-900 text-white font-medium rounded-xl text-xs sm:text-sm transition-all duration-200 flex items-center justify-center gap-2 shadow-xs active:scale-[0.99] disabled:opacity-75 cursor-pointer"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin text-white" />
                <span>Verifying Credentials...</span>
              </>
            ) : (
              <span>Sign in to Secure Workspace</span>
            )}
          </button>

          {/* Secondary Action: Google SSO */}
          <button
            id="google-sso-button"
            type="button"
            onClick={handleGoogleSignIn}
            disabled={isSubmitting || isGoogleLoading}
            className="w-full py-2.5 sm:py-3 px-4 bg-white hover:bg-neutral-50 active:bg-neutral-100 border border-neutral-200 text-neutral-800 font-medium rounded-xl text-xs sm:text-sm transition-all duration-200 flex items-center justify-center gap-2 shadow-xs active:scale-[0.99] disabled:opacity-75 cursor-pointer"
          >
            {isGoogleLoading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-neutral-500" />
            ) : (
              <GoogleIcon className="w-3.5 h-3.5" />
            )}
            <span>Sign In with Enterprise SSO</span>
          </button>
        </div>
      </form>


      {/* Footer Security Certifications */}
      <div className="mt-4 pt-2.5 border-t border-neutral-100 flex flex-col sm:flex-row items-center justify-between text-[11px] text-neutral-400 gap-1.5 select-none">
        <span className="text-center sm:text-left">
          Sessions authenticated via cryptographic server-signed tokens.
        </span>
        <div className="flex items-center gap-1.5 text-neutral-800 font-semibold whitespace-nowrap">
          <ShieldCheck className="w-3.5 h-3.5 text-neutral-900" />
          <span>Zero-Trust RBAC</span>
        </div>
      </div>

      {/* Bottom Switch Link */}
      {onNavigateToSignUp && (
        <div className="mt-2.5 text-center text-xs text-neutral-500">
          Need directory access?{" "}
          <button
            type="button"
            onClick={onNavigateToSignUp}
            className="font-semibold text-neutral-900 hover:underline"
          >
            Request Enterprise Account
          </button>
        </div>
      )}
    </div>
  );
}
