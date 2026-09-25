import { ChevronRight } from "lucide-react";
import { Badge } from "../../components/ui/Badge";
import type { PromptDef } from "../../lib/prompts";

/** Divided list of runnable questions. Shows the exact text that will be sent. */
export function PromptList({ prompts, onAsk }: { prompts: PromptDef[]; onAsk: (prompt: string) => void }) {
  return (
    <ul className="prompt-list">
      {prompts.map((p) => (
        <li key={p.prompt}>
          <button type="button" className="prompt-row" onClick={() => onAsk(p.prompt)}>
            <span className="prompt-copy">
              <span className="prompt-label">{p.label}</span>
              <span className="prompt-text">{p.prompt}</span>
            </span>
            {p.meta && <Badge>{p.meta}</Badge>}
            <ChevronRight size={16} aria-hidden="true" className="prompt-chevron" />
          </button>
        </li>
      ))}
    </ul>
  );
}
