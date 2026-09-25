import {
  BarChart3,
  FileText,
  FolderSearch,
  HelpCircle,
  Sparkles,
} from "lucide-react";
import type { UserIdentity } from "../../api";
import { NanviHeroAnimation } from "./NanviHeroAnimation";

interface Props {
  identity?: UserIdentity | null;
  onPick: (query: string) => void;
  disabled?: boolean;
}

export function EmptyStateBento({ identity, onPick, disabled = false }: Props) {
  const displayName = identity?.name || identity?.email?.split("@")[0] || "there";
  const firstName = displayName.split(" ")[0];
  const departmentOrRole = identity?.department || identity?.roles?.[0] || "Operations";

  return (
    <div className="empty-workspace-view" aria-label="Enterprise Assistant Workspace">
      {/* Main Hero Header & Value Proposition */}
      <div className="hero-header-section">
        <div className="hero-title-wrap">
          <h1 className="hero-greeting">
            NANVI AI <span className="hero-greeting-sub">Enterprise Assistant</span>
          </h1>
          <span className="hero-user-greet">Welcome back, {firstName} • Interactive Intelligence Ready</span>
        </div>
        <p className="hero-subtitle">
          Your company&apos;s knowledge, data, and operations — accessible through one AI assistant.
        </p>
      </div>

      {/* Centerpiece: Living NANVI AI Animated Robot with Interactive Hotspot Buttons */}
      <div className="hero-centerpiece-container">
        <NanviHeroAnimation onSelectSource={(q) => !disabled && onPick(q)} />
      </div>

      {/* Quick Starters / Suggested Row */}
      {/* Quick Starters / Suggested Row */}
      <div className="hero-starters-section">
        <div className="starters-label-row">
          <Sparkles size={13} className="sparkle-gold" aria-hidden="true" />
          <span>Quick starters for your workspace clearance:</span>
        </div>

        <div className="hero-bento-grid" style={{ width: "100%", maxWidth: "720px", margin: "4px auto 0" }}>
          <button
            type="button"
            className="hero-bento-card"
            disabled={disabled}
            onClick={() => onPick("Show standard operating procedures for vendor onboarding")}
          >
            <div className="bento-card-top">
              <span className="bento-card-icon tone-finance">
                <FileText size={16} aria-hidden="true" />
              </span>
              <span className="bento-tag tag-finance">SOP & Operations</span>
            </div>
            <div className="bento-card-title">Vendor Onboarding SOP</div>
            <p className="bento-card-desc">Standard operating procedures and compliance checks for new vendors</p>
            <div className="bento-card-action">
              <span>Ask assistant</span>
              <span className="action-arrow">→</span>
            </div>
          </button>

          <button
            type="button"
            className="hero-bento-card"
            disabled={disabled}
            onClick={() => onPick("Track quarterly logistics fulfillment and supply chain SLA")}
          >
            <div className="bento-card-top">
              <span className="bento-card-icon tone-engineering">
                <BarChart3 size={16} aria-hidden="true" />
              </span>
              <span className="bento-tag tag-engineering">Logistics & SLA</span>
            </div>
            <div className="bento-card-title">Supply Chain Performance</div>
            <p className="bento-card-desc">Quarterly fulfillment metrics and partner service level compliance</p>
            <div className="bento-card-action">
              <span>Run report query</span>
              <span className="action-arrow">→</span>
            </div>
          </button>

          <button
            type="button"
            className="hero-bento-card"
            disabled={disabled}
            onClick={() => onPick("Search team workspace files for office facility requests")}
          >
            <div className="bento-card-top">
              <span className="bento-card-icon tone-hr">
                <FolderSearch size={16} aria-hidden="true" />
              </span>
              <span className="bento-tag tag-hr">Knowledge Vault</span>
            </div>
            <div className="bento-card-title">Workspace & Facilities</div>
            <p className="bento-card-desc">Search team files for facility policies, desk allocation, and maintenance</p>
            <div className="bento-card-action">
              <span>Search vaults</span>
              <span className="action-arrow">→</span>
            </div>
          </button>

          <button
            type="button"
            className="hero-bento-card"
            disabled={disabled}
            onClick={() => onPick("What documents and resources are available in my authorized workspace?")}
          >
            <div className="bento-card-top">
              <span className="bento-card-icon tone-security">
                <HelpCircle size={16} aria-hidden="true" />
              </span>
              <span className="bento-tag tag-security">Security & Clearance</span>
            </div>
            <div className="bento-card-title">Workspace Directory</div>
            <p className="bento-card-desc">Overview of all vaults, documents, and database tools accessible to your role</p>
            <div className="bento-card-action">
              <span>View clearance map</span>
              <span className="action-arrow">→</span>
            </div>
          </button>
        </div>
      </div>
    </div>
  );
}
