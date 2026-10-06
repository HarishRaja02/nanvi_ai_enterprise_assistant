import React from "react";
import { HardDrive, Database, Mail, Cloud, Globe } from "lucide-react";

interface SourceOption {
  key: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
}

const SOURCES: SourceOption[] = [
  {
    key: "local",
    label: "Local Storage",
    icon: HardDrive,
    description: "Company files & documents on local disk",
  },
  {
    key: "database",
    label: "Database",
    icon: Database,
    description: "Invoices, contracts & business records",
  },
  {
    key: "email",
    label: "Email",
    icon: Mail,
    description: "Inbox communications & attachments",
  },
  {
    key: "drive",
    label: "Google Drive",
    icon: Cloud,
    description: "Google Workspace & Drive storage",
  },
  {
    key: "cloud",
    label: "Cloud",
    icon: Globe,
    description: "Enterprise cloud storage repositories",
  },
];

interface Props {
  onSelect: (sourceKey: string) => void;
  disabled?: boolean;
  selectedSource?: string;
}

export function SourceSelector({ onSelect, disabled = false, selectedSource }: Props) {
  return (
    <div className="source-selector-container">
      <div className="source-selector-title">
        Select a source to search:
      </div>
      <div className="source-selector-grid">
        {SOURCES.map((s) => {
          const Icon = s.icon;
          const isSelected = selectedSource === s.key;
          return (
            <button
              key={s.key}
              type="button"
              className={`source-selector-btn ${isSelected ? "selected" : ""}`}
              disabled={disabled}
              onClick={() => onSelect(s.key)}
              title={s.description}
            >
              <div className="source-selector-icon">
                <Icon className="w-5 h-5" />
              </div>
              <div className="source-selector-info">
                <span className="source-selector-label">{s.label}</span>
                <span className="source-selector-desc">{s.description}</span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
