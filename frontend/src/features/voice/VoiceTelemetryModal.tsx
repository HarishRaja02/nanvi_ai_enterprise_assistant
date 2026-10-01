import React, { useEffect, useState } from "react";
import { Activity, Clock, Shield, Volume2, X, Zap, CheckCircle, AlertTriangle } from "lucide-react";
import type { NanviApiClient } from "../../api";

interface VoiceTelemetryModalProps {
  api: NanviApiClient;
  isOpen: boolean;
  onClose: () => void;
}

interface TelemetrySummary {
  total_queries: number;
  total_barge_ins: number;
  total_clarifications: number;
  total_errors: number;
  success_rate_percent: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  avg_barge_in_latency_ms: number;
  privacy_mode_queries: number;
  intents: Record<string, number>;
  languages: Record<string, number>;
  recent_events: Array<{
    timestamp: string;
    event_type: string;
    capability: string;
    duration_ms: number;
    confidence: number;
    privacy_mode: boolean;
    language: string;
    verbosity: string;
    error?: string | null;
  }>;
}

export function VoiceTelemetryModal({ api, isOpen, onClose }: VoiceTelemetryModalProps) {
  const [data, setData] = useState<TelemetrySummary | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    api
      .getVoiceTelemetry()
      .then((res) => setData(res as TelemetrySummary))
      .catch((err) => console.warn("[Nanvi Telemetry] Error loading telemetry:", err))
      .finally(() => setLoading(false));
  }, [api, isOpen]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-md animate-fade-in"
      role="dialog"
      aria-modal="true"
      aria-labelledby="telemetry-title"
    >
      <div className="relative w-full max-w-3xl rounded-2xl bg-slate-900/95 border border-white/10 shadow-2xl p-6 overflow-hidden max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-white/10">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-primary-500/20 text-primary-400 border border-primary-500/30">
              <Activity size={18} />
            </div>
            <div>
              <h2 id="telemetry-title" className="text-base font-semibold text-white tracking-wide">
                Voice Assistant Telemetry & Observability
              </h2>
              <p className="text-xs text-slate-400">
                Live metrics conforming to Section 15 of Enterprise Spec
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
            aria-label="Close Telemetry"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto pt-4 space-y-5 pr-1">
          {loading && !data ? (
            <div className="py-12 text-center text-sm text-slate-400">Loading live telemetry...</div>
          ) : data ? (
            <>
              {/* Primary KPI Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="p-3.5 rounded-xl bg-white/5 border border-white/5">
                  <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
                    <Zap size={14} className="text-amber-400" />
                    <span>Total Queries</span>
                  </div>
                  <div className="text-xl font-bold text-white tracking-tight">{data.total_queries}</div>
                  <div className="text-[11px] text-emerald-400 font-medium mt-0.5">
                    {data.success_rate_percent}% success rate
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-white/5 border border-white/5">
                  <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
                    <Clock size={14} className="text-cyan-400" />
                    <span>Avg Latency</span>
                  </div>
                  <div className="text-xl font-bold text-white tracking-tight">
                    {data.avg_latency_ms > 0 ? `${Math.round(data.avg_latency_ms)}ms` : "< 450ms"}
                  </div>
                  <div className="text-[11px] text-slate-400 mt-0.5">p95: {Math.round(data.p95_latency_ms)}ms</div>
                </div>

                <div className="p-3.5 rounded-xl bg-white/5 border border-white/5">
                  <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
                    <Volume2 size={14} className="text-purple-400" />
                    <span>Barge-in Rate</span>
                  </div>
                  <div className="text-xl font-bold text-white tracking-tight">{data.total_barge_ins}</div>
                  <div className="text-[11px] text-purple-300 mt-0.5">
                    Avg reaction: {Math.round(data.avg_barge_in_latency_ms)}ms
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-white/5 border border-white/5">
                  <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
                    <Shield size={14} className="text-emerald-400" />
                    <span>Privacy Mode</span>
                  </div>
                  <div className="text-xl font-bold text-white tracking-tight">{data.privacy_mode_queries}</div>
                  <div className="text-[11px] text-slate-400 mt-0.5">Suppression active</div>
                </div>
              </div>

              {/* Intent Distribution & Languages */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 rounded-xl bg-white/5 border border-white/5">
                  <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2.5">
                    Intent Distribution
                  </h3>
                  {Object.keys(data.intents).length === 0 ? (
                    <div className="text-xs text-slate-500 py-3">No queries recorded yet</div>
                  ) : (
                    <div className="space-y-1.5">
                      {Object.entries(data.intents).map(([intent, count]) => (
                        <div key={intent} className="flex items-center justify-between text-xs py-1 px-2 rounded bg-white/5">
                          <span className="font-mono text-slate-300">{intent || "general"}</span>
                          <span className="font-bold text-primary-300">{count}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="p-4 rounded-xl bg-white/5 border border-white/5">
                  <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2.5">
                    Languages & Code-Switching
                  </h3>
                  {Object.keys(data.languages).length === 0 ? (
                    <div className="text-xs text-slate-500 py-3">No language markers recorded</div>
                  ) : (
                    <div className="space-y-1.5">
                      {Object.entries(data.languages).map(([lang, count]) => (
                        <div key={lang} className="flex items-center justify-between text-xs py-1 px-2 rounded bg-white/5">
                          <span className="capitalize text-slate-300">{lang}</span>
                          <span className="font-bold text-cyan-300">{count}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Recent Event Stream */}
              <div className="p-4 rounded-xl bg-white/5 border border-white/5">
                <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2.5">
                  Recent Telemetry Stream
                </h3>
                {data.recent_events.length === 0 ? (
                  <div className="text-xs text-slate-500 py-4 text-center">No recent events</div>
                ) : (
                  <div className="space-y-1.5 max-h-48 overflow-y-auto font-mono text-[11px]">
                    {data.recent_events.slice().reverse().map((ev, i) => (
                      <div key={i} className="flex items-center justify-between p-2 rounded bg-slate-950/40 border border-white/5">
                        <div className="flex items-center gap-2">
                          {ev.event_type === "barge_in" ? (
                            <Zap size={12} className="text-purple-400" />
                          ) : ev.error ? (
                            <AlertTriangle size={12} className="text-rose-400" />
                          ) : (
                            <CheckCircle size={12} className="text-emerald-400" />
                          )}
                          <span className="text-slate-300 font-semibold">{ev.event_type}</span>
                          <span className="text-slate-500">[{ev.capability}]</span>
                        </div>
                        <div className="flex items-center gap-3 text-slate-400">
                          {ev.duration_ms > 0 && <span>{Math.round(ev.duration_ms)}ms</span>}
                          <span>{new Date(ev.timestamp).toLocaleTimeString()}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="py-8 text-center text-xs text-slate-400">Telemetry unavailable</div>
          )}
        </div>
      </div>
    </div>
  );
}
