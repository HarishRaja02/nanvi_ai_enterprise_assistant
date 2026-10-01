import { PromptList } from "./PromptList";
import { WORKSPACES } from "./config";
import { visiblePrompts } from "../../lib/prompts";
import { CompanyFolderPicker } from "../../components/ui/CompanyFolderPicker";
import type { NanviApiClient } from "../../api";
import type { Permission, View } from "../../lib/access";

type Props = { view: View; permissions: readonly Permission[]; onAsk: (prompt: string) => void; api?: NanviApiClient };

export function WorkspacePage({ view, permissions, onAsk, api }: Props) {
  const def = WORKSPACES[view];
  if (!def) return null;
  return (
    <div className="page">
      <div className="workspace-hero-banner">
        <h1 className="workspace-hero-title">{view} Workspace</h1>
        <p className="page-intro">{def.intro}</p>
        <span className="workspace-meta-tag">⚡ Enterprise Guided Inquiries</span>
      </div>

      {/* Show folder picker on Data and Knowledge workspaces */}
      {(view === "Data" || view === "Knowledge") && api && <CompanyFolderPicker api={api} />}

      <p className="page-hint">Choosing a question runs it in the assistant with role-based document access.</p>
      {def.sections.map((section) => {
        const prompts = visiblePrompts(section.prompts, permissions);
        if (prompts.length === 0) return null;
        const headingId = `sec-${section.title.toLowerCase().replace(/\W+/g, "-")}`;
        return (
          <section key={section.title} className="page-section" aria-labelledby={headingId}>
            <h2 id={headingId}>{section.title}</h2>
            <PromptList prompts={prompts} onAsk={onAsk} />
          </section>
        );
      })}
    </div>
  );
}
