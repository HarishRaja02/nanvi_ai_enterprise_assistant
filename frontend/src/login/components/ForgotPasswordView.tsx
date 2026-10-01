import React, { useState } from "react";
import { ArrowLeft, CheckCircle2, Loader2, Mail } from "lucide-react";

interface ForgotPasswordViewProps {
  onBackToSignIn: () => void;
  defaultEmail?: string;
}

export function ForgotPasswordView({
  onBackToSignIn,
  defaultEmail = "",
}: ForgotPasswordViewProps) {
  const [email, setEmail] = useState(defaultEmail || "harishraja806@gmail.com");
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;

    setIsLoading(true);
    setTimeout(() => {
      setIsLoading(false);
      setIsSubmitted(true);
    }, 800);
  };

  return (
    <div id="forgot-password-container" className="w-full max-w-[420px] mx-auto">
      <button
        onClick={onBackToSignIn}
        className="inline-flex items-center gap-1.5 text-xs text-neutral-500 hover:text-neutral-900 mb-3 transition-colors"
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
          Enter your email to receive recovery instructions
        </p>
      </div>

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
              We've dispatched a secure password reset link to:
            </p>
            <p className="text-xs font-semibold text-neutral-800 mt-0.5">
              {email}
            </p>
          </div>
          <p className="text-[11px] text-neutral-400">
            Did not receive the email? Check spam folder or try again in 60s.
          </p>
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
              htmlFor="forgot-email-input"
              className="block text-sm font-medium text-neutral-800 mb-1.5"
            >
              Email Address
            </label>
            <div className="relative">
              <input
                id="forgot-email-input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Enter your registered email"
                required
                className="w-full pl-10 pr-4 py-3 bg-[#f8f9fa] border border-neutral-200/90 rounded-xl text-neutral-900 text-sm placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:bg-white transition-all shadow-xs"
              />
              <Mail className="w-4 h-4 text-neutral-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
            </div>
          </div>

          <button
            id="send-reset-button"
            type="submit"
            disabled={isLoading}
            className="w-full py-3.5 px-6 bg-black hover:bg-neutral-800 active:bg-neutral-900 text-white font-medium rounded-xl text-sm transition-all duration-200 flex items-center justify-center gap-2 shadow-sm cursor-pointer"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Sending link...</span>
              </>
            ) : (
              <span>Send Recovery Link</span>
            )}
          </button>

          <div className="text-center pt-2">
            <button
              type="button"
              onClick={onBackToSignIn}
              className="text-xs font-medium text-neutral-500 hover:text-neutral-900 hover:underline"
            >
              Remember your password? Sign In
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
