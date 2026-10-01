import React from "react";
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Table as TableIcon,
  FileText,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  Info,
  Calendar,
  ArrowRight,
  Download,
  Sparkles,
  ShieldCheck,
  Mail,
  Database,
  Globe,
} from "lucide-react";
import type {
  UISpec,
  KPICardData,
  TableCardData,
  SourceListData,
  TimelineCardData,
  StatusCardData,
  ActionCardData,
} from "./voiceTypes";

interface GlassUICardProps {
  spec: UISpec;
  onActionClick?: (intent: string) => void;
  isHighlighted?: boolean;
  className?: string;
}

export const GlassUICard: React.FC<GlassUICardProps> = ({
  spec,
  onActionClick,
  isHighlighted = false,
  className = "",
}) => {
  switch (spec.card_type) {
    case "kpi_card":
      return <KPICardRenderer data={spec.data as KPICardData} isHighlighted={isHighlighted} className={className} />;
    case "table_card":
      return <TableCardRenderer data={spec.data as TableCardData} isHighlighted={isHighlighted} className={className} />;
    case "source_list":
      return <SourceListRenderer data={spec.data as SourceListData} isHighlighted={isHighlighted} className={className} />;
    case "timeline_card":
      return <TimelineCardRenderer data={spec.data as TimelineCardData} isHighlighted={isHighlighted} className={className} />;
    case "status_card":
      return <StatusCardRenderer data={spec.data as StatusCardData} isHighlighted={isHighlighted} className={className} />;
    case "action_card":
      return (
        <ActionCardRenderer
          data={spec.data as ActionCardData}
          onActionClick={onActionClick}
          isHighlighted={isHighlighted}
          className={className}
        />
      );
    default:
      return null;
  }
};

/* -------------------------------------------------------------------------- */
/* 1. KPI Card Renderer                                                       */
/* -------------------------------------------------------------------------- */
const KPICardRenderer: React.FC<{ data: KPICardData; className?: string; isHighlighted?: boolean }> = ({
  data,
  className = "",
  isHighlighted = false,
}) => {
  const isUp = data.trend === "up";
  const isDown = data.trend === "down";

  return (
    <div
      className={`glass-kpi-card relative overflow-hidden rounded-2xl p-5 border ${
        isHighlighted
          ? "border-cyan-400 ring-2 ring-cyan-400/50 shadow-cyan-500/25 scale-[1.01]"
          : "border-white/10"
      } bg-slate-900/60 backdrop-blur-xl shadow-xl transition-all duration-300 hover:border-cyan-500/30 ${className}`}
      data-testid="ui-kpi-card"
    >
      <div className="flex items-center justify-between gap-3 mb-2">
        <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">
          {data.metric_label || "Key Metric"}
        </span>
        <Sparkles className="w-3.5 h-3.5 text-cyan-400 opacity-60" />
      </div>

      <div className="flex items-baseline gap-3">
        <span className="text-3xl sm:text-4xl font-extrabold tracking-tight bg-gradient-to-r from-white via-slate-100 to-cyan-200 bg-clip-text text-transparent">
          {data.value}
        </span>
        {data.unit && (
          <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
            {data.unit}
          </span>
        )}
      </div>

      {(data.trend || data.trend_value) && (
        <div className="flex items-center gap-2 mt-3 pt-3 border-t border-white/5">
          <div
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${
              isUp
                ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/20"
                : isDown
                ? "bg-rose-500/15 text-rose-400 border border-rose-500/20"
                : "bg-slate-700/30 text-slate-400 border border-slate-600/30"
            }`}
          >
            {isUp && <TrendingUp className="w-3 h-3" />}
            {isDown && <TrendingDown className="w-3 h-3" />}
            {!isUp && !isDown && <Minus className="w-3 h-3" />}
            <span>{data.trend_value || (isUp ? "Increased" : "Decreased")}</span>
          </div>
          {data.comparison_label && (
            <span className="text-xs text-slate-400">{data.comparison_label}</span>
          )}
        </div>
      )}
    </div>
  );
};

/* -------------------------------------------------------------------------- */
/* 2. Table Card Renderer                                                     */
/* -------------------------------------------------------------------------- */
const TableCardRenderer: React.FC<{ data: TableCardData; className?: string; isHighlighted?: boolean }> = ({
  data,
  className = "",
  isHighlighted = false,
}) => {
  const columns = data.columns || [];
  const rows = data.rows || [];

  return (
    <div
      className={`glass-table-card rounded-2xl p-4 border ${
        isHighlighted
          ? "border-cyan-400 ring-2 ring-cyan-400/50 shadow-cyan-500/25 scale-[1.01]"
          : "border-white/10"
      } bg-slate-900/60 backdrop-blur-xl shadow-xl transition-all duration-300 hover:border-cyan-500/20 ${className}`}
      data-testid="ui-table-card"
    >
      <div className="flex items-center justify-between mb-3 px-1">
        <div className="flex items-center gap-2">
          <TableIcon className="w-4 h-4 text-cyan-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            {data.title || "Data Breakdown"}
          </span>
        </div>
        {data.total_rows ? (
          <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-white/5 text-slate-400 border border-white/10">
            {data.truncated ? `Showing ${rows.length} of ${data.total_rows}` : `${rows.length} rows`}
          </span>
        ) : null}
      </div>

      <div className="overflow-x-auto rounded-xl border border-white/5">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-white/10 bg-white/[0.03]">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={`py-2.5 px-3 font-semibold text-slate-300 tracking-wider ${
                    col.align === "right"
                      ? "text-right"
                      : col.align === "center"
                      ? "text-center"
                      : "text-left"
                  }`}
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {rows.map((row, rIdx) => (
              <tr
                key={rIdx}
                className="transition-colors hover:bg-white/[0.04]"
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={`py-2 px-3 text-slate-300 ${
                      col.align === "right"
                        ? "text-right font-mono"
                        : col.align === "center"
                        ? "text-center"
                        : "text-left"
                    }`}
                  >
                    {row[col.key] !== undefined ? String(row[col.key]) : "—"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

/* -------------------------------------------------------------------------- */
/* 3. Source List Renderer                                                    */
/* -------------------------------------------------------------------------- */
const SourceListRenderer: React.FC<{ data: SourceListData; className?: string; isHighlighted?: boolean }> = ({
  data,
  className = "",
  isHighlighted = false,
}) => {
  const sources = data.sources || [];

  const getSourceIcon = (type?: string) => {
    switch (type?.toLowerCase()) {
      case "email":
        return <Mail className="w-3.5 h-3.5 text-sky-400" />;
      case "db":
        return <Database className="w-3.5 h-3.5 text-emerald-400" />;
      case "web":
        return <Globe className="w-3.5 h-3.5 text-amber-400" />;
      default:
        return <FileText className="w-3.5 h-3.5 text-violet-400" />;
    }
  };

  return (
    <div
      className={`glass-source-card rounded-2xl p-4 border border-white/10 bg-slate-900/60 backdrop-blur-xl shadow-xl transition-all duration-300 ${className}`}
      data-testid="ui-source-list"
    >
      <div className="flex items-center gap-2 mb-3 px-1">
        <ShieldCheck className="w-4 h-4 text-emerald-400" />
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
          Verified Sources ({sources.length})
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {sources.map((src, idx) => (
          <div
            key={idx}
            className="group flex flex-col gap-1 p-2.5 rounded-xl border border-white/5 bg-white/[0.02] hover:bg-white/[0.05] hover:border-cyan-500/20 transition-all duration-200"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 min-w-0">
                {getSourceIcon(src.file_type)}
                <span className="text-xs font-medium text-slate-200 truncate">
                  {src.title}
                </span>
              </div>
              {src.relevance_score !== undefined && src.relevance_score > 0 && (
                <span className="shrink-0 text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  {Math.round(src.relevance_score * 100)}%
                </span>
              )}
            </div>
            {src.snippet && (
              <p className="text-[11px] text-slate-400 line-clamp-2 leading-relaxed">
                {src.snippet}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

/* -------------------------------------------------------------------------- */
/* 4. Timeline Card Renderer                                                  */
/* -------------------------------------------------------------------------- */
const TimelineCardRenderer: React.FC<{
  data: TimelineCardData;
  className?: string;
  isHighlighted?: boolean;
}> = ({
  data,
  className = "",
  isHighlighted = false,
}) => {
  const items = data.items || [];

  return (
    <div
      className={`glass-timeline-card rounded-2xl p-4 border ${
        isHighlighted
          ? "border-cyan-400 ring-2 ring-cyan-400/50 shadow-cyan-500/25 scale-[1.01]"
          : "border-white/10"
      } bg-slate-900/60 backdrop-blur-xl shadow-xl transition-all duration-300 ${className}`}
      data-testid="ui-timeline-card"
    >
      <div className="flex items-center gap-2 mb-4 px-1">
        <Calendar className="w-4 h-4 text-cyan-400" />
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
          {data.title || "Timeline"}
        </span>
      </div>

      <div className="relative pl-4 space-y-3 before:absolute before:left-1.5 before:top-2 before:bottom-2 before:w-[2px] before:bg-white/10">
        {items.map((item, idx) => (
          <div key={idx} className="relative group flex flex-col gap-0.5">
            <div className="absolute -left-[14px] top-1.5 w-2 h-2 rounded-full bg-cyan-400 ring-4 ring-slate-900 shadow-sm shadow-cyan-400/50" />
            <div className="flex items-baseline gap-2">
              <span className="text-[11px] font-mono font-medium text-cyan-300">
                {item.timestamp}
              </span>
              <span className="text-xs font-semibold text-slate-200">
                {item.title}
              </span>
            </div>
            {item.detail && (
              <p className="text-[11px] text-slate-400 leading-relaxed">
                {item.detail}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

/* -------------------------------------------------------------------------- */
/* 5. Status Card Renderer                                                    */
/* -------------------------------------------------------------------------- */
const StatusCardRenderer: React.FC<{
  data: StatusCardData;
  className?: string;
  isHighlighted?: boolean;
}> = ({
  data,
  className = "",
  isHighlighted = false,
}) => {
  const getStatusConfig = (status: string) => {
    switch (status) {
      case "success":
        return {
          icon: <CheckCircle2 className="w-5 h-5 text-emerald-400" />,
          badgeClass: "bg-emerald-500/10 border-emerald-500/20 text-emerald-400",
        };
      case "warning":
        return {
          icon: <AlertTriangle className="w-5 h-5 text-amber-400" />,
          badgeClass: "bg-amber-500/10 border-amber-500/20 text-amber-400",
        };
      case "error":
        return {
          icon: <AlertCircle className="w-5 h-5 text-rose-400" />,
          badgeClass: "bg-rose-500/10 border-rose-500/20 text-rose-400",
        };
      default:
        return {
          icon: <Info className="w-5 h-5 text-cyan-400" />,
          badgeClass: "bg-cyan-500/10 border-cyan-500/20 text-cyan-400",
        };
    }
  };

  const config = getStatusConfig(data.status);

  return (
    <div
      className={`glass-status-card flex items-start gap-3 rounded-2xl p-4 border ${
        isHighlighted
          ? "border-cyan-400 ring-2 ring-cyan-400/50 shadow-cyan-500/25 scale-[1.01]"
          : "border-white/10"
      } bg-slate-900/60 backdrop-blur-xl shadow-xl transition-all duration-300 ${className}`}
      data-testid="ui-status-card"
    >
      <div className="shrink-0 p-2 rounded-xl bg-white/5 border border-white/10">
        {config.icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-xs font-bold text-slate-100">{data.title}</span>
          <span
            className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full border ${config.badgeClass}`}
          >
            {data.status}
          </span>
        </div>
        {data.detail && (
          <p className="text-xs text-slate-400 leading-relaxed">{data.detail}</p>
        )}
      </div>
    </div>
  );
};

/* -------------------------------------------------------------------------- */
/* 6. Action Card Renderer                                                    */
/* -------------------------------------------------------------------------- */
const ActionCardRenderer: React.FC<{
  data: ActionCardData;
  onActionClick?: (intent: string) => void;
  className?: string;
  isHighlighted?: boolean;
}> = ({ data, onActionClick, className = "", isHighlighted = false }) => {
  const actions = data.actions || [];

  return (
    <div
      className={`glass-action-card rounded-2xl p-4 border ${
        isHighlighted
          ? "border-cyan-400 ring-2 ring-cyan-400/50 shadow-cyan-500/25 scale-[1.01]"
          : "border-white/10"
      } bg-slate-900/60 backdrop-blur-xl shadow-xl transition-all duration-300 ${className}`}
      data-testid="ui-action-card"
    >
      <div className="flex items-center gap-2 mb-3 px-1">
        <Sparkles className="w-4 h-4 text-cyan-400" />
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
          {data.title || "Suggested Next Steps"}
        </span>
      </div>

      <div className="flex flex-wrap gap-2">
        {actions.map((act, idx) => {
          const isPrimary = act.variant === "primary" || idx === 0;
          return (
            <button
              key={idx}
              type="button"
              onClick={() => onActionClick?.(act.intent)}
              className={`group inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition-all duration-200 cursor-pointer ${
                isPrimary
                  ? "bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-md shadow-cyan-500/20 hover:shadow-cyan-500/40 hover:-translate-y-0.5"
                  : "bg-white/5 hover:bg-white/10 text-slate-200 border border-white/10 hover:border-cyan-500/30 hover:-translate-y-0.5"
              }`}
            >
              <span>{act.label}</span>
              {act.icon === "download" ? (
                <Download className="w-3 h-3 transition-transform group-hover:translate-y-0.5" />
              ) : (
                <ArrowRight className="w-3 h-3 transition-transform group-hover:translate-x-0.5" />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
};
