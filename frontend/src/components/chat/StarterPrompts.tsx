import { Database, FileText, Mail, type LucideIcon } from "lucide-react";
import type { PromptDef } from "../../lib/prompts";

const AREA_ICON: Record<string, LucideIcon> = { documents: FileText, email: Mail, data: Database };

type Props = { prompts: Array<PromptDef & { area: string }>; onPick: (prompt: string) => void; disabled: boolean };

export function StarterPrompts({ prompts, onPick, disabled }: Props) {
  return (
    <ul className="starters" aria-label="Suggested questions">
      {prompts.map((p) => {
        const Icon = AREA_ICON[p.area] ?? FileText;
        return (
          <li key={p.prompt}>
            <button type="button" className="starter" disabled={disabled} onClick={() => onPick(p.prompt)}>
              <Icon size={18} aria-hidden="true" />
              <span className="starter-copy">
                <span className="starter-label">{p.label}</span>
                <span className="starter-prompt">{p.prompt}</span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
