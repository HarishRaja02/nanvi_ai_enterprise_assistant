/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useEffect } from "react";
import { AuthView } from "./types";
import { BrandLogo } from "./components/BrandLogo";
import { QuotePanel } from "./components/QuotePanel";
import { LoginForm } from "./components/LoginForm";
import { ForgotPasswordView } from "./components/ForgotPasswordView";
import { RegisterForm } from "./components/RegisterForm";
import ambientRibbons from "./assets/images/ambient_bg_ribbons_1789978811594.jpg";

export interface LoginGatewayProps {
  error?: string;
  loggedOut?: boolean;
  onLogin: (username: string, password: string) => Promise<void> | void;
  loading?: boolean;
}

export function EnterpriseLoginGateway({
  error = "",
  loggedOut = false,
  onLogin,
  loading = false,
}: LoginGatewayProps) {
  const [currentView, setCurrentView] = useState<AuthView>("signin");
  const [signedOutBanner, setSignedOutBanner] = useState(true);
  const [mobileTab, setMobileTab] = useState<"auth" | "quote">("auth");

  useEffect(() => {
    if (loggedOut) {
      setSignedOutBanner(true);
      setCurrentView("signin");
    }
  }, [loggedOut]);

  return (
    <div className="relative min-h-screen w-full bg-[#030305] text-slate-900 flex items-center justify-center p-2 sm:p-3 md:p-4 lg:p-5 overflow-y-auto selection:bg-slate-900 selection:text-white font-sans">
      {/* Outer Atmospheric Ribbon Trails */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
        <img
          src={ambientRibbons}
          alt=""
          className="w-full h-full object-cover opacity-60 mix-blend-screen scale-105 blur-[2px]"
          referrerPolicy="no-referrer"
          aria-hidden="true"
        />
        {/* Soft radial vignette */}
        <div className="absolute inset-0 bg-radial from-transparent via-black/40 to-black/90" />
      </div>

      {/* Main Dual-Panel Container: Balanced proportions fitting within viewport without scrolling */}
      <div
        id="nanvi-enterprise-login-card"
        className="relative z-10 w-full max-w-[1220px] xl:max-w-[1260px] min-h-[580px] lg:min-h-[610px] max-h-[92vh] bg-white rounded-[28px] sm:rounded-[36px] shadow-2xl overflow-hidden grid grid-cols-1 lg:grid-cols-12 p-3 sm:p-4 lg:p-5 gap-4 lg:gap-6 border border-white/10 my-auto"
      >
        {/* Mobile View Toggle (Visible on small screens only) */}
        <div className="lg:hidden col-span-1 flex items-center justify-center pt-2">
          <div className="inline-flex p-1 bg-slate-100 rounded-full text-xs font-medium">
            <button
              type="button"
              onClick={() => setMobileTab("auth")}
              className={`px-4 py-1.5 rounded-full transition-all ${
                mobileTab === "auth"
                  ? "bg-white text-slate-950 shadow-xs font-semibold"
                  : "text-slate-500 hover:text-slate-900"
              }`}
            >
              Enterprise Gateway
            </button>
            <button
              type="button"
              onClick={() => setMobileTab("quote")}
              className={`px-4 py-1.5 rounded-full transition-all ${
                mobileTab === "quote"
                  ? "bg-white text-slate-950 shadow-xs font-semibold"
                  : "text-slate-500 hover:text-slate-900"
              }`}
            >
              Artwork & Quote
            </button>
          </div>
        </div>

        {/* Left Column: Visual Quote Panel with Neon Ribbons (5 of 12 cols on desktop) */}
        <div
          className={`w-full h-full ${
            mobileTab === "quote" ? "block" : "hidden"
          } lg:block lg:col-span-5`}
        >
          <QuotePanel />
        </div>

        {/* Right Column: Nanvi AI Enterprise Gateway (7 of 12 cols on desktop) */}
        <div
          className={`w-full h-full bg-white rounded-[22px] sm:rounded-[28px] flex flex-col justify-between py-3.5 sm:py-5 px-4 sm:px-7 md:px-8 lg:px-8 xl:px-10 lg:col-span-7 overflow-y-auto lg:overflow-visible ${
            mobileTab === "auth" ? "flex" : "hidden"
          } lg:flex`}
        >
          {/* Top Brand Header */}
          <div className="flex items-center justify-between pb-2.5 sm:pb-3 border-b border-neutral-100">
            <BrandLogo />
            <div className="hidden sm:flex items-center gap-1.5 text-[11px] font-medium text-neutral-500 bg-neutral-100/90 px-3 py-1 rounded-full border border-neutral-200/60 select-none">
              <span className="w-1.5 h-1.5 rounded-full bg-neutral-900" />
              <span>Gateway v2.6.4</span>
            </div>
          </div>

          {/* Form Content Area */}
          <div className="py-2 sm:py-3 my-auto">
            {currentView === "signin" && (
              <LoginForm
                onLogin={onLogin}
                loading={loading}
                externalError={error}
                onNavigateToSignUp={() => setCurrentView("signup")}
                onNavigateToForgot={() => setCurrentView("forgot")}
                signedOutBanner={signedOutBanner}
                onDismissBanner={() => setSignedOutBanner(false)}
              />
            )}

            {currentView === "forgot" && (
              <ForgotPasswordView
                onBackToSignIn={() => setCurrentView("signin")}
              />
            )}

            {currentView === "signup" && (
              <RegisterForm
                onSuccess={() => onLogin("employee", "nanviSecure2026!")}
                onNavigateToSignIn={() => setCurrentView("signin")}
              />
            )}
          </div>

          {/* Bottom subtle compliance disclaimer */}
          <div className="text-center pt-1.5 border-t border-slate-100">
            <p className="text-[10px] sm:text-[11px] text-slate-400">
              Nanvi AI Enterprise Assistant Platform · End-to-End Encrypted Zero-Trust Perimeter
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default EnterpriseLoginGateway;
