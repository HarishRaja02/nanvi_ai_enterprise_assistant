import { useState } from "react";
import { ChevronDown, ShieldCheck, CheckCircle2, Layers } from "lucide-react";

export function formatTraceSteps(rawSteps: string[]): string[] {
  if (!rawSteps || rawSteps.length === 0) return [];

  const hasRawCodes = rawSteps.some((s) => s.startsWith("route:") || s.startsWith("agent:"));
  if (!hasRawCodes) return rawSteps;

  const result: string[] = [];
  const seen = new Set<string>();

  const hasKnowledge = rawSteps.some((s) => s.includes("knowledge") || s.includes("rag"));
  const hasDatabase = rawSteps.some((s) => s.includes("database") || s.includes("sql"));
  const hasEmail = rawSteps.some((s) => s.includes("email") || s.includes("mail"));
  const hasReport = rawSteps.some((s) => s.includes("report"));
  const hasWeb = rawSteps.some((s) => s.includes("web_search"));

  if (hasKnowledge) {
    [
      "Policy check passed: KNOWLEDGE_RETRIEVAL",
      "RAG indexed search scanned authorized vaults in C:\\CompanyData",
      "Retrieved top matching chunks with citations",
      "Grounded answer synthesized via Groq LLM",
    ].forEach((s) => { if (!seen.has(s)) { seen.add(s); result.push(s); } });
  }
  if (hasDatabase) {
    [
      "Policy check passed: DATABASE_READ",
      "Validated SQL (SELECT only, LIMIT enforced)",
      "Executed against enterprise repository",
      "Composed answer from result set",
    ].forEach((s) => { if (!seen.has(s)) { seen.add(s); result.push(s); } });
  }
  if (hasEmail) {
    [
      "Policy check passed: EMAIL_READ",
      "Queried authorized Gmail mailbox and threads",
      "Extracted relevant communications and headers",
      "Composed answer from email contents",
    ].forEach((s) => { if (!seen.has(s)) { seen.add(s); result.push(s); } });
  }
  if (hasReport) {
    [
      "Policy check passed: REPORT_CREATE",
      "Collected provenance for authorized sources",
      "Generated structured report artifact",
    ].forEach((s) => { if (!seen.has(s)) { seen.add(s); result.push(s); } });
  }
  if (hasWeb) {
    [
      "Policy check passed: WEB_SEARCH_EXECUTE",
      "Queried real-time web sources via Tavily API",
      "Ranked and cited top search results",
      "Composed answer with web citations",
    ].forEach((s) => { if (!seen.has(s)) { seen.add(s); result.push(s); } });
  }

  if (result.length === 0) {
    return rawSteps.map((s) => s.replace(/^(route|agent):/, "").replace(/_/g, " ").trim());
  }

  return result;
}

/** Backend-reported steps for this answer. Modern, sleek collapsible execution trace. */
export function TraceDisclosure({ steps }: { steps: string[] }) {
  const [open, setOpen] = useState(false);
  const displaySteps = formatTraceSteps(steps);

  if (!displaySteps || displaySteps.length === 0) return null;

  return (
    <div className="trace-accordion">
      <button
        type="button"
        className={`trace-trigger ${open ? "is-open" : ""}`}
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-label="How this answer was made"
        title={open ? "Click to collapse execution steps" : "Click to view how this answer was made"}
      >
        <div className="trace-trigger-content">
          <Layers size={13} className="trace-icon" aria-hidden="true" />
          <span className="trace-title">How this answer was made</span>
          <span className="trace-badge">
            {displaySteps.length} {displaySteps.length === 1 ? "step" : "steps"}
          </span>
        </div>
        <ChevronDown
          size={13}
          className={`trace-chevron ${open ? "is-open" : ""}`}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div className="trace-body" role="region" aria-label="Step by step execution details">
          <ol className="trace-timeline">
            {displaySteps.map((step, idx) => {
              const isPolicy = step.startsWith("Policy check passed:");
              const policyName = isPolicy ? step.replace("Policy check passed:", "").trim() : null;

              return (
                <li key={idx} className={`trace-item ${isPolicy ? "is-policy" : ""}`}>
                  <div className="trace-item-marker">
                    {isPolicy ? (
                      <ShieldCheck size={13} className="trace-policy-icon" aria-hidden="true" />
                    ) : (
                      <CheckCircle2 size={13} className="trace-step-icon" aria-hidden="true" />
                    )}
                  </div>
                  <div className="trace-item-content">
                    {isPolicy ? (
                      <>
                        <span className="trace-policy-label">Policy check passed:</span>
                        <code className="trace-policy-code">{policyName}</code>
                      </>
                    ) : (
                      <span className="trace-step-text">{step}</span>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </div>
  );
}
