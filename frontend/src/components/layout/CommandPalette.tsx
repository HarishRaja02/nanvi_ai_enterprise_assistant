import { useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3,
  BookOpen,
  Calendar,
  Compass,
  FilePlus2,
  FileText,
  Globe,
  Mail,
  Moon,
  PlusCircle,
  Search,
  Sun,
  Users,
  X,
  Zap,
} from "lucide-react";
import type { View } from "../../lib/access";

interface Props {
  open: boolean;
  onClose: () => void;
  onNavigate: (view: View) => void;
  onAsk: (prompt: string) => void;
  onNewConversation: () => void;
  ragEnabled?: boolean;
  onToggleRag?: (enabled: boolean) => void;
  theme?: "light" | "dark";
  onToggleTheme?: () => void;
}

interface PaletteItem {
  id: string;
  category: "Actions" | "Workspaces" | "Queries";
  title: string;
  description: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  run: () => void;
}

export function CommandPalette({
  open,
  onClose,
  onNavigate,
  onAsk,
  onNewConversation,
  ragEnabled = true,
  onToggleRag,
  theme = "light",
  onToggleTheme,
}: Props) {
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const items: PaletteItem[] = useMemo(() => {
    return [
      // Actions
      {
        id: "act-new",
        category: "Actions",
        title: "New Conversation",
        description: "Start a fresh discussion with Nanvi",
        icon: PlusCircle,
        run: () => {
          onNewConversation();
          onClose();
        },
      },
      {
        id: "act-theme",
        category: "Actions",
        title: `Switch to ${theme === "dark" ? "Light" : "Dark"} Mode`,
        description: `Toggle application theme (currently ${theme})`,
        icon: theme === "dark" ? Sun : Moon,
        run: () => {
          onToggleTheme?.();
          onClose();
        },
      },
      {
        id: "act-rag",
        category: "Actions",
        title: `Toggle RAG (${ragEnabled ? "Currently Enabled" : "Currently Disabled"})`,
        description: "Toggle retrieval from C:\\CompanyData vaults",
        icon: Zap,
        run: () => {
          onToggleRag?.(!ragEnabled);
          onClose();
        },
      },
      // Workspaces
      {
        id: "ws-chat",
        category: "Workspaces",
        title: "Assistant Chat Workspace",
        description: "Interactive AI enterprise chat interface",
        icon: Compass,
        run: () => {
          onNavigate("Chat");
          onClose();
        },
      },
      {
        id: "ws-knowledge",
        category: "Workspaces",
        title: "Knowledge Vaults",
        description: "Explore indexed contracts, policies, and documents",
        icon: BookOpen,
        run: () => {
          onNavigate("Knowledge");
          onClose();
        },
      },
      {
        id: "ws-data",
        category: "Workspaces",
        title: "Business Data Platform",
        description: "Query enterprise database and structured records",
        icon: BarChart3,
        run: () => {
          onNavigate("Data");
          onClose();
        },
      },
      {
        id: "ws-reports",
        category: "Workspaces",
        title: "Reports Studio",
        description: "Generate and export reports in PDF and Excel",
        icon: FilePlus2,
        run: () => {
          onNavigate("Reports");
          onClose();
        },
      },
      {
        id: "ws-finance",
        category: "Workspaces",
        title: "Finance & Payables",
        description: "Invoices, forecasts, and expense compliance",
        icon: BarChart3,
        run: () => {
          onNavigate("Finance");
          onClose();
        },
      },
      {
        id: "ws-hr",
        category: "Workspaces",
        title: "HR & People",
        description: "Handbook policies, vacation, and headcount",
        icon: Users,
        run: () => {
          onNavigate("HR");
          onClose();
        },
      },
      {
        id: "ws-email",
        category: "Workspaces",
        title: "Email & Threads",
        description: "Search corporate mailbox and communications",
        icon: Mail,
        run: () => {
          onNavigate("Email");
          onClose();
        },
      },
      // Quick Queries
      {
        id: "q-invoices",
        category: "Queries",
        title: "Show Overdue Invoices",
        description: "Retrieve vendor payables with amounts and due dates",
        icon: FileText,
        run: () => {
          onAsk("Show overdue invoices");
          onClose();
        },
      },
      {
        id: "q-sla",
        category: "Queries",
        title: "Customer SLAs & Support Guarantees",
        description: "Inspect customer contract service levels",
        icon: BookOpen,
        run: () => {
          onAsk("What are the customer SLAs and support guarantees?");
          onClose();
        },
      },
      {
        id: "q-leave",
        category: "Queries",
        title: "Employee Leave & Vacation Policy",
        description: "Review handbook guidelines for time off",
        icon: Calendar,
        run: () => {
          onAsk("What is our leave and vacation policy in HR?");
          onClose();
        },
      },
      {
        id: "q-phoenix",
        category: "Queries",
        title: "Project Phoenix Milestones",
        description: "Check status of Project Phoenix and deliverables",
        icon: Compass,
        run: () => {
          onAsk("What is the status of Project Phoenix in Projects vault?");
          onClose();
        },
      },
      {
        id: "q-web",
        category: "Queries",
        title: "Search the Web",
        description: "Live internet query for external market data",
        icon: Globe,
        run: () => {
          onAsk("Search the web for enterprise AI agent trends and market news");
          onClose();
        },
      },
      {
        id: "q-rep-pdf",
        category: "Queries",
        title: "Generate Overdue Invoices Report (PDF)",
        description: "Compose verified PDF download",
        icon: FilePlus2,
        run: () => {
          onAsk("Generate a report on overdue invoices in PDF");
          onClose();
        },
      },
    ];
  }, [onClose, onNavigate, onAsk, onNewConversation, ragEnabled, onToggleRag, theme, onToggleTheme]);

  // Filter items
  const filtered = useMemo(() => {
    if (!query.trim()) return items;
    const q = query.toLowerCase();
    return items.filter(
      (item) =>
        item.title.toLowerCase().includes(q) ||
        item.description.toLowerCase().includes(q) ||
        item.category.toLowerCase().includes(q),
    );
  }, [items, query]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  // Focus input when opened
  useEffect(() => {
    if (open) {
      setQuery("");
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  // Handle keyboard navigation
  useEffect(() => {
    if (!open) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((prev) => (prev + 1) % (filtered.length || 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((prev) => (prev - 1 + (filtered.length || 1)) % (filtered.length || 1));
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (filtered[selectedIndex]) {
          filtered[selectedIndex].run();
        }
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, filtered, selectedIndex, onClose]);

  if (!open) return null;

  return (
    <div className="palette-backdrop" onClick={onClose} aria-modal="true" role="dialog">
      <div className="palette-card" onClick={(e) => e.stopPropagation()}>
        {/* Search Input Bar */}
        <div className="palette-search-row">
          <Search size={18} className="palette-search-icon" aria-hidden="true" />
          <input
            ref={inputRef}
            type="text"
            className="palette-input"
            placeholder="Type a command, workspace, or question… (↑↓ to select, ↵ to run)"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Command palette search"
          />
          <button type="button" className="palette-close-btn" onClick={onClose} aria-label="Close command palette">
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        {/* Results List */}
        <div className="palette-results" role="listbox">
          {filtered.length > 0 ? (
            filtered.map((item, idx) => {
              const Icon = item.icon;
              const isSelected = idx === selectedIndex;

              return (
                <div
                  key={item.id}
                  className={`palette-item ${isSelected ? "is-selected" : ""}`}
                  role="option"
                  aria-selected={isSelected}
                  onClick={() => item.run()}
                  onMouseEnter={() => setSelectedIndex(idx)}
                >
                  <div className="palette-item-icon">
                    <Icon size={16} aria-hidden="true" />
                  </div>
                  <div className="palette-item-content">
                    <div className="palette-item-title-row">
                      <span className="palette-item-title">{item.title}</span>
                      <span className="palette-item-cat">{item.category}</span>
                    </div>
                    <span className="palette-item-desc">{item.description}</span>
                  </div>
                </div>
              );
            })
          ) : (
            <div className="palette-empty">
              <span>No matching commands or actions found.</span>
            </div>
          )}
        </div>

        {/* Palette Footer */}
        <div className="palette-footer">
          <span><kbd>↑</kbd> <kbd>↓</kbd> navigate</span>
          <span><kbd>Enter</kbd> select</span>
          <span><kbd>Esc</kbd> close</span>
        </div>
      </div>
    </div>
  );
}
