import React, { useState } from "react";
import { ArrowLeft, CheckCircle2, Loader2, Mail, User, AlertCircle, ExternalLink } from "lucide-react";
import { api } from "../../api";

interface ForgotPasswordViewProps {
  onBackToSignIn: () => void;
  defaultEmail?: string;
  defaultUsername?: string;
  onOpenResetLink?: (token: string) => void;
}

export function ForgotPasswordView({
  onBackToSignIn,
  defaultEmail = "",
  defaultUsername = "",
  onOpenResetLink,
}: ForgotPasswordViewProps) {
  const [username, setUsername] = useState(defaultUsername || "");
  const [email, setEmail] = useState(defaultEmail || "");
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [devResetLink, setDevResetLink] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage("");

    if (!username.trim()) {
      setErrorMessage("Please enter your User ID or Username.");
      return;
    }
    if (!email.trim()) {
      setErrorMessage("Please enter your registered email address.");
      return;
    }

    setIsLoading(true);
    try {
      const resp = await api.forgotPassword(username.trim(), email.trim());
      setIsSubmitted(true);
      if (resp.dev_reset_link) {
        setDevResetLink(resp.dev_reset_link);
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to process recovery request.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleOpenDevLink = () => {
    if (!devResetLink) return;
    const url = new URL(devResetLink, window.location.origin);
    const token = url.searchParams.get("token");
    if (token && onOpenResetLink) {
      onOpenResetLink(token);
    } else {
      window.location.href = devResetLink;
    }
  };

  return (
    <div id="forgot-password-container" className="w-full max-w-[420px] mx-auto">
      <button
        onClick={onBackToSignIn}
        className="inline-flex items-center gap-1.5 text-xs text-neutral-500 hover:text-neutral-900 mb-3 transition-colors cursor-pointer"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        <span>Back to login</span>
      </button>

      <div className="text-center mb-4">
        <h1
          id="forgot-heading"
          className="font-serif text-2xl sm:text-3xl font-normal text-neutral-900 tracking-tight leading-tight"
        >
          Reset Password
        </h1>
        <p className="mt-1 text-xs text-neutral-500 font-normal">
          Provide your enterprise username and email to verify your identity
        </p>
      </div>

      {errorMessage && (
        <div
          id="forgot-error-banner"
          className="mb-3 p-2.5 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2 animate-in fade-in duration-200"
        >
          <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}

      {isSubmitted ? (
        <div className="p-6 rounded-2xl bg-neutral-50 border border-neutral-200/80 text-center space-y-4 animate-in fade-in zoom-in-95 duration-200">
          <div className="w-12 h-12 rounded-full bg-neutral-900 text-white flex items-center justify-center mx-auto shadow-xs">
            <CheckCircle2 className="w-6 h-6 stroke-[2]" />
          </div>
          <div>
            <h2 className="font-semibold text-neutral-900 text-base">
              Check Your Inbox
            </h2>
            <p className="text-xs text-neutral-500 mt-1">
              If your username and email match our directory, we've dispatched a secure recovery link to:
            </p>
            <p className="text-xs font-semibold text-neutral-800 mt-0.5">
              {email}
            </p>
          </div>
          <p className="text-[11px] text-neutral-400">
            Link expires in 15 minutes. Check spam folder if not received.
          </p>

          {devResetLink && (
            <div className="p-3 bg-indigo-50/80 border border-indigo-200 rounded-xl text-left space-y-2">
              <div className="flex items-center justify-between text-indigo-900 text-xs font-semibold">
                <span>Dev / Demo Mode Active</span>
                <span className="text-[10px] bg-indigo-200/60 text-indigo-800 px-1.5 py-0.5 rounded">Local</span>
              </div>
              <p className="text-[11px] text-indigo-700 leading-relaxed">
                Click below to immediately open the generated password reset link without checking email:
              </p>
              <button
                type="button"
                onClick={handleOpenDevLink}
                className="w-full py-2 px-3 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium rounded-lg flex items-center justify-center gap-1.5 transition cursor-pointer"
              >
                <span>Open Reset Link</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          <button
            onClick={onBackToSignIn}
            className="w-full py-2.5 px-4 bg-black text-white text-xs font-medium rounded-xl hover:bg-neutral-800 transition cursor-pointer"
          >
            Return to Sign In
          </button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="forgot-username-input"
              className="block text-xs font-medium text-neutral-800 mb-1"
            >
              Enterprise User ID / Username
            </label>
            <div className="relative">
              <input
                id="forgot-username-input"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="e.g. ceo, maya.nair, admin"
                required
                className="w-full pl-10 pr-4 py-2.5 bg-[#f8f9fa] border border-neutral-200/90 rounded-xl text-neutral-900 text-xs sm:text-sm placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:bg-white transition-all shadow-xs"
              />
              <User className="w-4 h-4 text-neutral-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
            </div>
          </div>

          <div>
            <label
              htmlFor="forgot-email-input"
              className="block text-xs font-medium text-neutral-800 mb-1"
            >
              Registered Email Address
            </label>
            <div className="relative">
              <input
                id="forgot-email-input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="e.g. user@company.com"
                required
                className="w-full pl-10 pr-4 py-2.5 bg-[#f8f9fa] border border-neutral-200/90 rounded-xl text-neutral-900 text-xs sm:text-sm placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:bg-white transition-all shadow-xs"
              />
              <Mail className="w-4 h-4 text-neutral-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
            </div>
          </div>

          <button
            id="send-reset-button"
            type="submit"
            disabled={isLoading}
            className="w-full py-3 px-6 bg-black hover:bg-neutral-800 active:bg-neutral-900 text-white font-medium rounded-xl text-xs sm:text-sm transition-all duration-200 flex items-center justify-center gap-2 shadow-sm cursor-pointer"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Verifying credentials...</span>
              </>
            ) : (
              <span>Send Recovery Link</span>
            )}
          </button>

          <div className="text-center pt-2">
            <button
              type="button"
              onClick={onBackToSignIn}
              className="text-xs font-medium text-neutral-500 hover:text-neutral-900 hover:underline cursor-pointer"
            >
              Remember your password? Sign In
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
