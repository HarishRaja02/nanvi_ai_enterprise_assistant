import React, { useState, useEffect } from "react";
import { ArrowLeft, CheckCircle2, Eye, EyeOff, Loader2, Lock, AlertCircle, ShieldAlert } from "lucide-react";
import { api } from "../../api";

interface ResetPasswordViewProps {
  token: string;
  onBackToSignIn: () => void;
  onRequestNewLink?: () => void;
}

export function ResetPasswordView({
  token,
  onBackToSignIn,
  onRequestNewLink,
}: ResetPasswordViewProps) {
  const [isValidating, setIsValidating] = useState(true);
  const [tokenError, setTokenError] = useState("");
  const [accountInfo, setAccountInfo] = useState<{ username: string; email: string; display_name: string } | null>(null);

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [isSuccess, setIsSuccess] = useState(false);

  useEffect(() => {
    let isMounted = true;
    async function verify() {
      if (!token) {
        setTokenError("Missing password reset token. Please request a new recovery link.");
        setIsValidating(false);
        return;
      }
      try {
        const res = await api.verifyResetToken(token);
        if (isMounted) {
          if (res.valid) {
            setAccountInfo({ username: res.username, email: res.email, display_name: res.display_name });
          } else {
            setTokenError("The password recovery link is invalid or has expired.");
          }
        }
      } catch (err) {
        if (isMounted) {
          setTokenError(err instanceof Error ? err.message : "The recovery link is invalid or expired.");
        }
      } finally {
        if (isMounted) setIsValidating(false);
      }
    }
    verify();
    return () => {
      isMounted = false;
    };
  }, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError("");

    if (newPassword.length < 6) {
      setSubmitError("Password must be at least 6 characters long.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setSubmitError("Passwords do not match. Please re-type your new password.");
      return;
    }

    setIsSubmitting(true);
    try {
      await api.resetPasswordWithToken(token, newPassword);
      setIsSuccess(true);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to reset password. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isValidating) {
    return (
      <div id="reset-password-loading" className="w-full max-w-[420px] mx-auto text-center py-12 space-y-3">
        <Loader2 className="w-8 h-8 animate-spin mx-auto text-neutral-800" />
        <p className="text-sm font-medium text-neutral-700">Verifying secure recovery token...</p>
        <p className="text-xs text-neutral-400">Validating single-use cryptographic token</p>
      </div>
    );
  }

  if (tokenError) {
    return (
      <div id="reset-token-error-container" className="w-full max-w-[420px] mx-auto text-center space-y-4">
        <div className="w-12 h-12 rounded-full bg-red-100 text-red-600 flex items-center justify-center mx-auto">
          <ShieldAlert className="w-6 h-6 stroke-[2]" />
        </div>
        <div>
          <h2 className="font-semibold text-neutral-900 text-lg">Invalid or Expired Link</h2>
          <p className="text-xs text-neutral-600 mt-1 max-w-[320px] mx-auto">
            {tokenError}
          </p>
        </div>
        <div className="pt-2 space-y-2">
          {onRequestNewLink && (
            <button
              onClick={onRequestNewLink}
              className="w-full py-2.5 px-4 bg-neutral-900 text-white text-xs font-medium rounded-xl hover:bg-neutral-800 transition cursor-pointer"
            >
              Request New Recovery Link
            </button>
          )}
          <button
            onClick={onBackToSignIn}
            className="w-full py-2.5 px-4 bg-neutral-100 text-neutral-700 text-xs font-medium rounded-xl hover:bg-neutral-200 transition cursor-pointer"
          >
            Back to Sign In
          </button>
        </div>
      </div>
    );
  }

  if (isSuccess) {
    return (
      <div id="reset-password-success-container" className="w-full max-w-[420px] mx-auto text-center space-y-4 animate-in fade-in zoom-in-95 duration-200">
        <div className="w-12 h-12 rounded-full bg-emerald-600 text-white flex items-center justify-center mx-auto shadow-xs">
          <CheckCircle2 className="w-6 h-6 stroke-[2]" />
        </div>
        <div>
          <h2 className="font-semibold text-neutral-900 text-lg">Password Successfully Updated</h2>
          <p className="text-xs text-neutral-500 mt-1">
            Your enterprise account password has been updated. You can now log in with your new credentials.
          </p>
        </div>
        <button
          id="return-to-signin-success-button"
          onClick={onBackToSignIn}
          className="w-full py-3 px-4 bg-black text-white text-xs sm:text-sm font-medium rounded-xl hover:bg-neutral-800 transition cursor-pointer"
        >
          Sign In with New Password
        </button>
      </div>
    );
  }

  return (
    <div id="reset-password-container" className="w-full max-w-[420px] mx-auto">
      <button
        onClick={onBackToSignIn}
        className="inline-flex items-center gap-1.5 text-xs text-neutral-500 hover:text-neutral-900 mb-3 transition-colors cursor-pointer"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        <span>Cancel</span>
      </button>

      <div className="text-center mb-4">
        <h1
          id="reset-heading"
          className="font-serif text-2xl sm:text-3xl font-normal text-neutral-900 tracking-tight leading-tight"
        >
          Create New Password
        </h1>
        {accountInfo && (
          <p className="mt-1 text-xs text-neutral-500 font-normal">
            Resetting credentials for <span className="font-semibold text-neutral-800">{accountInfo.username}</span> ({accountInfo.email})
          </p>
        )}
      </div>

      {submitError && (
        <div
          id="reset-error-banner"
          className="mb-3 p-2.5 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2 animate-in fade-in duration-200"
        >
          <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
          <span>{submitError}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label
            htmlFor="new-password-input"
            className="block text-xs font-medium text-neutral-800 mb-1"
          >
            New Password
          </label>
          <div className="relative">
            <input
              id="new-password-input"
              type={showPassword ? "text" : "password"}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="Minimum 6 characters"
              required
              minLength={6}
              className="w-full pl-10 pr-10 py-2.5 bg-[#f8f9fa] border border-neutral-200/90 rounded-xl text-neutral-900 text-xs sm:text-sm placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:bg-white transition-all shadow-xs"
            />
            <Lock className="w-4 h-4 text-neutral-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-700 p-0.5 focus:outline-none"
            >
              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>

        <div>
          <label
            htmlFor="confirm-password-input"
            className="block text-xs font-medium text-neutral-800 mb-1"
          >
            Confirm New Password
          </label>
          <div className="relative">
            <input
              id="confirm-password-input"
              type={showPassword ? "text" : "password"}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Re-enter your new password"
              required
              minLength={6}
              className="w-full pl-10 pr-10 py-2.5 bg-[#f8f9fa] border border-neutral-200/90 rounded-xl text-neutral-900 text-xs sm:text-sm placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:bg-white transition-all shadow-xs"
            />
            <Lock className="w-4 h-4 text-neutral-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          </div>
        </div>

        <button
          id="confirm-reset-button"
          type="submit"
          disabled={isSubmitting}
          className="w-full py-3 px-6 bg-black hover:bg-neutral-800 active:bg-neutral-900 text-white font-medium rounded-xl text-xs sm:text-sm transition-all duration-200 flex items-center justify-center gap-2 shadow-sm cursor-pointer"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Updating password...</span>
            </>
          ) : (
            <span>Update Password</span>
          )}
        </button>
      </form>
    </div>
  );
}
