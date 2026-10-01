import React, { useState } from "react";
import { Eye, EyeOff, Loader2, AlertCircle, CheckCircle2 } from "lucide-react";
import { GoogleIcon } from "./GoogleIcon";
import { UserSession } from "../types";

interface RegisterFormProps {
  onSuccess: (session: UserSession) => void;
  onNavigateToSignIn: () => void;
}

export function RegisterForm({
  onSuccess,
  onNavigateToSignIn,
}: RegisterFormProps) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [agreeTerms, setAgreeTerms] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage("");
    setSuccessMessage("");

    if (!fullName.trim()) {
      setErrorMessage("Please enter your full name.");
      return;
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email.trim())) {
      setErrorMessage("Please enter a valid email address.");
      return;
    }
    if (password.length < 6) {
      setErrorMessage("Password must be at least 6 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setErrorMessage("Passwords do not match.");
      return;
    }
    if (!agreeTerms) {
      setErrorMessage("Please agree to the Terms of Service to continue.");
      return;
    }

    setIsLoading(true);

    setTimeout(() => {
      setIsLoading(false);
      setSuccessMessage("Account created successfully! Preparing dashboard...");

      const session: UserSession = {
        id: "usr_" + Math.random().toString(36).substring(2, 9),
        name: fullName.trim(),
        username: email.split("@")[0].toLowerCase(),
        email: email.trim().toLowerCase(),
        avatarUrl: `https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80`,
        roleId: "employee",
        roleTitle: "Enterprise Member",
        department: "Operations",
        accessLevel: "Tier 2: Standard Access",
        sessionToken: "jwt_sec_" + Math.random().toString(36).substring(2, 16),
        lastLogin: "Just now",
        permissions: ["Workplace Copilot", "Document Synthesis", "Personal Queue"],
      };

      localStorage.setItem("nanvi_enterprise_session", JSON.stringify(session));

      setTimeout(() => {
        onSuccess(session);
      }, 700);
    }, 900);
  };

  return (
    <div id="register-form-container" className="w-full max-w-[620px] mx-auto">
      <div className="text-center mb-3">
        <h1
          id="register-heading"
          className="font-serif text-2xl sm:text-3xl font-normal text-neutral-900 tracking-tight leading-tight"
        >
          Create Account
        </h1>
        <p className="mt-1 text-xs text-neutral-500 font-normal">
          Start your journey and manage your plans seamlessly
        </p>
      </div>

      {errorMessage && (
        <div
          id="register-error-banner"
          className="mb-3 p-2.5 rounded-lg bg-red-50/90 border border-red-200/70 text-red-700 text-xs flex items-start gap-2 animate-in fade-in duration-200"
        >
          <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
          <span>{errorMessage}</span>
        </div>
      )}

      {successMessage && (
        <div
          id="register-success-banner"
          className="mb-3 p-2.5 rounded-lg bg-neutral-100 border border-neutral-200 text-neutral-900 text-xs flex items-center gap-2 animate-in fade-in duration-200"
        >
          <CheckCircle2 className="w-4 h-4 text-neutral-900 shrink-0" />
          <span>{successMessage}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-2.5">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          <div>
            <label
              htmlFor="register-name-input"
              className="block text-xs font-medium text-neutral-800 mb-1"
            >
              Full Name
            </label>
            <input
              id="register-name-input"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="John Doe"
              required
              className="w-full px-3 py-2 bg-[#f8f9fa] border border-neutral-200/90 rounded-lg text-neutral-900 text-xs sm:text-sm placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:bg-white transition-all"
            />
          </div>

          <div>
            <label
              htmlFor="register-email-input"
              className="block text-xs font-medium text-neutral-800 mb-1"
            >
              Email
            </label>
            <input
              id="register-email-input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Enter your email"
              required
              className="w-full px-3 py-2 bg-[#f8f9fa] border border-neutral-200/90 rounded-lg text-neutral-900 text-xs sm:text-sm placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:bg-white transition-all"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          <div>
            <label
              htmlFor="register-password-input"
              className="block text-xs font-medium text-neutral-800 mb-1"
            >
              Password
            </label>
            <div className="relative">
              <input
                id="register-password-input"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Create a password"
                required
                className="w-full pl-3 pr-10 py-2 bg-[#f8f9fa] border border-neutral-200/90 rounded-lg text-neutral-900 text-xs sm:text-sm placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:bg-white transition-all"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-700 p-1"
              >
                {showPassword ? (
                  <EyeOff className="w-3.5 h-3.5" />
                ) : (
                  <Eye className="w-3.5 h-3.5" />
                )}
              </button>
            </div>
          </div>

          <div>
            <label
              htmlFor="register-confirm-password-input"
              className="block text-xs font-medium text-neutral-800 mb-1"
            >
              Confirm Password
            </label>
            <input
              id="register-confirm-password-input"
              type={showPassword ? "text" : "password"}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Re-enter password"
              required
              className="w-full px-3 py-2 bg-[#f8f9fa] border border-neutral-200/90 rounded-lg text-neutral-900 text-xs sm:text-sm placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:bg-white transition-all"
            />
          </div>
        </div>

        <div className="pt-0.5">
          <label className="flex items-start gap-2 cursor-pointer select-none">
            <input
              id="terms-checkbox"
              type="checkbox"
              checked={agreeTerms}
              onChange={(e) => setAgreeTerms(e.target.checked)}
              className="w-3.5 h-3.5 mt-0.5 rounded border-neutral-300 text-neutral-950 accent-neutral-950 focus:ring-neutral-900"
            />
            <span className="text-xs text-neutral-600 leading-tight">
              I agree to the{" "}
              <span className="font-medium text-neutral-900 underline">
                Terms of Service
              </span>{" "}
              and{" "}
              <span className="font-medium text-neutral-900 underline">
                Privacy Policy
              </span>
            </span>
          </label>
        </div>

        <button
          id="create-account-button"
          type="submit"
          disabled={isLoading}
          className="w-full py-2.5 px-6 bg-black hover:bg-neutral-800 active:bg-neutral-900 text-white font-medium rounded-lg text-xs sm:text-sm transition-all duration-200 flex items-center justify-center gap-2 shadow-xs cursor-pointer mt-2"
        >
          {isLoading ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              <span>Creating account...</span>
            </>
          ) : (
            <span>Create Account</span>
          )}
        </button>
      </form>

      <div className="mt-3 text-center text-xs text-neutral-600">
        Already have an account?{" "}
        <button
          id="switch-to-signin-link"
          type="button"
          onClick={onNavigateToSignIn}
          className="font-semibold text-neutral-900 hover:underline focus:outline-none"
        >
          Sign In
        </button>
      </div>
    </div>
  );
}
