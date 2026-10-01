import { memo } from "react";
import type { ContextMetric } from "../../lib/contextIntelligence";

interface Props {
  metrics: ContextMetric[];
  title?: string;
  onMetricClick?: (m: ContextMetric) => void;
  className?: string;
}

export function BentoMetricsBase({ metrics, title, onMetricClick, className = "" }: Props) {
  if (!metrics || metrics.length === 0) return null;

  return (
    <div className={`bento-metrics-container ${className}`}>
      {title && <div className="bento-metrics-title">{title}</div>}
      <div className="bento-grid">
        {metrics.map((m) => (
          <div
            key={m.id}
            className={`bento-card tone-${m.tone || "primary"}${onMetricClick ? " is-interactive" : ""}`}
            onClick={() => onMetricClick?.(m)}
            role={onMetricClick ? "button" : undefined}
            tabIndex={onMetricClick ? 0 : undefined}
            onKeyDown={(e) => {
              if (onMetricClick && (e.key === "Enter" || e.key === " ")) {
                e.preventDefault();
                onMetricClick(m);
              }
            }}
          >
            <div className="bento-head">
              <span className="bento-label truncate">{m.label}</span>
              {m.tone && <span className={`bento-dot dot-${m.tone}`} aria-hidden="true" />}
            </div>
            <div className="bento-val tabular truncate">{m.value}</div>
            {m.subtext && <div className="bento-sub truncate">{m.subtext}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

export const BentoMetrics = memo(BentoMetricsBase);
