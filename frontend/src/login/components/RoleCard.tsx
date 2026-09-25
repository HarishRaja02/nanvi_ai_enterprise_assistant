import {
  Building2,
  DollarSign,
  Users,
  BarChart3,
  User,
  ShieldCheck,
} from "lucide-react";
import { RoleProfile } from "../types";

interface RoleCardProps {
  role: RoleProfile;
  isSelected: boolean;
  onSelect: (role: RoleProfile) => void;
}

export function RoleCard({ role, isSelected, onSelect }: RoleCardProps) {
  const renderIcon = () => {
    const iconClass = isSelected
      ? "w-4 h-4 text-white transition-colors"
      : "w-4 h-4 text-neutral-800 group-hover:text-black transition-colors";

    switch (role.id) {
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
        return <User className={iconClass} />;
    }
  };

  return (
    <button
      type="button"
      id={`role-card-${role.id}`}
      onClick={() => onSelect(role)}
      className={`relative p-2 sm:p-2.5 rounded-xl text-center flex flex-col items-center justify-center transition-all duration-200 border cursor-pointer group select-none min-h-[64px] ${
        isSelected
          ? "bg-neutral-950 text-white border-neutral-950 shadow-sm ring-1 ring-neutral-950/20"
          : "bg-[#fbfbfb] hover:bg-neutral-100/90 border-neutral-200/85 hover:border-neutral-300 text-neutral-900 shadow-2xs"
      }`}
    >
      <div className="mb-1 flex items-center justify-center transition-transform duration-200 group-hover:scale-105">
        {renderIcon()}
      </div>
      <span
        className={`font-semibold text-xs tracking-tight block leading-tight ${
          isSelected ? "text-white" : "text-neutral-900"
        }`}
      >
        {role.title}
      </span>
      <span
        className={`text-[10px] font-normal block mt-0.5 truncate max-w-full ${
          isSelected ? "text-neutral-300" : "text-neutral-500"
        }`}
      >
        {role.department}
      </span>
    </button>
  );
}
