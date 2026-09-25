import { UserSession } from "../types";
import {
  LogOut,
  ShieldCheck,
  Building2,
  DollarSign,
  Users,
  BarChart3,
  User,
  Cpu,
  CheckCircle2,
  Sparkles,
} from "lucide-react";

interface DashboardViewProps {
  session: UserSession;
  onLogout: () => void;
}

export function DashboardView({ session, onLogout }: DashboardViewProps) {
  const getRoleIcon = () => {
    const iconClass = "w-6 h-6 text-neutral-900";
    switch (session.roleId) {
      case "ceo":
        return <Building2 className={iconClass} />;
      case "finance":
        return <DollarSign className={iconClass} />;
      case "hr":
        return <Users className={iconClass} />;
      case "manager":
        return <BarChart3 className={iconClass} />;
      case "employee":
        return <User className={iconClass} />;
      case "itadmin":
        return <ShieldCheck className={iconClass} />;
      default:
        return <Cpu className={iconClass} />;
    }
  };

  return (
    <div
      id="nanvi-enterprise-workspace"
      className="w-full max-w-[500px] mx-auto py-2 text-left"
    >
      {/* Top Welcome Banner */}
      <div className="text-center mb-6">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-neutral-100 border border-neutral-200 text-neutral-800 text-xs font-medium mb-3 select-none">
          <ShieldCheck className="w-3.5 h-3.5 text-neutral-900" />
          <span>Nanvi Zero-Trust Session Active</span>
        </div>
        <h1 className="font-serif text-3xl sm:text-4xl font-normal text-neutral-900 tracking-tight">
          Enterprise Workspace
        </h1>
        <p className="mt-1.5 text-xs sm:text-sm text-neutral-500">
          Authenticated as{" "}
          <span className="font-semibold text-neutral-800">{session.name}</span>
        </p>
      </div>

      {/* Main Profile Info Card */}
      <div className="bg-[#fbfbfc] border border-neutral-200 rounded-2xl p-5 space-y-4 shadow-sm">
        {/* Role Header */}
        <div className="flex items-center justify-between pb-3 border-b border-neutral-200/80">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-white border border-neutral-200 flex items-center justify-center shadow-xs">
              {getRoleIcon()}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-semibold text-neutral-900 text-base">
                  {session.roleTitle}
                </span>
                <span className="text-[10px] uppercase font-semibold tracking-wider px-2 py-0.5 rounded bg-neutral-900 text-white">
                  {session.department}
                </span>
              </div>
              <p className="text-xs text-neutral-500 font-mono mt-0.5">
                @{session.username} · {session.email}
              </p>
            </div>
          </div>
          <div className="text-right">
            <span className="text-[10px] text-neutral-400 block uppercase tracking-wider font-semibold">
              Security Level
            </span>
            <span className="text-xs font-semibold text-neutral-800">
              {session.accessLevel}
            </span>
          </div>
        </div>

        {/* Permissions & Capabilities Grid */}
        <div>
          <span className="text-[10px] uppercase tracking-[0.16em] font-semibold text-neutral-400 block mb-2">
            Active Enterprise Permissions & Assistant Tools
          </span>
          <div className="grid grid-cols-2 gap-2">
            {session.permissions.map((perm, idx) => (
              <div
                key={idx}
                className="p-2.5 rounded-lg bg-white border border-neutral-200/90 text-xs text-neutral-800 flex items-center gap-2"
              >
                <CheckCircle2 className="w-3.5 h-3.5 text-neutral-900 shrink-0" />
                <span className="font-medium truncate">{perm}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Live Session Telemetry */}
        <div className="p-3 bg-white border border-neutral-200/80 rounded-xl space-y-1.5 text-xs text-neutral-600 font-mono">
          <div className="flex justify-between">
            <span className="text-neutral-400">Gateway:</span>
            <span className="text-neutral-800">/enterprise/auth/zero-trust</span>
          </div>
          <div className="flex justify-between">
            <span className="text-neutral-400">Token Sig:</span>
            <span className="text-neutral-800 truncate max-w-[180px]">
              {session.sessionToken}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-neutral-400">Login:</span>
            <span className="text-neutral-800">{session.lastLogin}</span>
          </div>
        </div>

        <div className="p-3 bg-neutral-100 border border-neutral-200 rounded-xl text-xs text-neutral-700 flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-neutral-900 shrink-0" />
          <span>
            Nanvi Enterprise Assistant Platform copilot is initialized and ready.
          </span>
        </div>
      </div>

      {/* Sign Out Button */}
      <div className="mt-5">
        <button
          id="workspace-sign-out-button"
          onClick={onLogout}
          className="w-full py-3.5 px-6 bg-black hover:bg-neutral-850 active:bg-neutral-900 text-white font-medium rounded-xl text-sm transition-all duration-200 flex items-center justify-center gap-2 cursor-pointer shadow-sm"
        >
          <LogOut className="w-4 h-4" />
          <span>Sign Out / Switch Enterprise Role</span>
        </button>
      </div>
    </div>
  );
}
