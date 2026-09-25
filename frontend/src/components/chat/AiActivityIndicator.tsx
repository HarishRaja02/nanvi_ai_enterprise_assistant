import { useEffect, useState } from "react";
import { Check, Loader2 } from "lucide-react";

interface Props {
  ragEnabled?: boolean;
}

interface Step {
  id: string;
  label: string;
  detail: string;
}

export function AiActivityIndicator({ ragEnabled = true }: Props) {
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [elapsed, setElapsed] = useState(0);

  const steps: Step[] = [
    {
      id: "step-understand",
      label: "Understanding request & intent",
      detail: "Parsing query context & parameters",
    },
    {
      id: "step-search",
      label: ragEnabled ? "Searching authorized knowledge vaults" : "Scanning enterprise records & data",
      detail: ragEnabled ? "Hybrid vector embeddings & BM25 lexical search" : "Direct database & service retrieval",
    },
    {
      id: "step-analyze",
      label: "Analyzing context & RBAC clearance",
      detail: "Verifying document permissions against user roles",
    },
    {
      id: "step-synthesize",
      label: "Synthesizing verified response",
      detail: "Formulating grounded answer with provenance citations",
    },
  ];

  useEffect(() => {
    const start = Date.now();
    const interval = setInterval(() => {
      const now = Date.now();
      const diff = Math.floor((now - start) / 1000);
      setElapsed(diff);

      // Advance progressive steps over realistic elapsed intervals
      if (diff < 1) {
        setCurrentStepIndex(0);
      } else if (diff < 2) {
        setCurrentStepIndex(1);
      } else if (diff < 4) {
        setCurrentStepIndex(2);
      } else {
        setCurrentStepIndex(3);
      }
    }, 500);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="ai-activity-card" role="status" aria-label="AI Activity Progress">
      <div className="ai-activity-header">
        <div className="ai-activity-bot">
          <span className="avatar avatar-bot" aria-hidden="true">N</span>
          <div className="ai-activity-meta">
            <span className="ai-activity-author">Nanvi Assistant</span>
            <span className="ai-activity-elapsed">{elapsed > 0 ? `${elapsed}s elapsed` : "Processing…"}</span>
          </div>
        </div>

        <div className="ai-activity-status-pill">
          <span className="rag-pulse-dot" aria-hidden="true" />
          <span>Active</span>
        </div>
      </div>

      <ol className="ai-activity-steps">
        {steps.map((step, idx) => {
          const isDone = idx < currentStepIndex;
          const isCurrent = idx === currentStepIndex;
          const isPending = idx > currentStepIndex;

          return (
            <li
              key={step.id}
              className={`ai-activity-step ${isDone ? "is-done" : ""} ${isCurrent ? "is-current" : ""} ${isPending ? "is-pending" : ""}`}
            >
              <div className="ai-step-indicator">
                {isDone && <Check size={12} className="ai-step-check" aria-hidden="true" />}
                {isCurrent && <Loader2 size={13} className="ai-step-spinner spin" aria-hidden="true" />}
                {isPending && <span className="ai-step-dot" aria-hidden="true" />}
              </div>

              <div className="ai-step-content">
                <span className="ai-step-label">{step.label}</span>
                {isCurrent && <span className="ai-step-detail">{step.detail}</span>}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
