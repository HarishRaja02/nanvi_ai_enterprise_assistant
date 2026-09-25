import { useState } from "react";
import { Sparkles, ArrowRight, ChevronDown } from "lucide-react";
import type { ContextSuggestion } from "../../lib/contextIntelligence";

interface Props {
  suggestions: ContextSuggestion[];
  onSelect: (text: string) => void;
  disabled?: boolean;
}

export function ContextualSuggestions({ suggestions, onSelect, disabled = false }: Props) {
  const [isCollapsed, setIsCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem("nanvi_suggestions_collapsed") === "true";
    } catch {
      return false;
    }
  });

  if (!suggestions || suggestions.length === 0) return null;

  const toggleCollapsed = () => {
    setIsCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("nanvi_suggestions_collapsed", String(next));
      } catch {
        // ignore storage errors
      }
      return next;
    });
  };

  return (
    <div className={`context-suggestions ${isCollapsed ? "is-collapsed" : ""}`} role="region" aria-label="Contextual suggestions">
      <div
        className="suggestions-header"
        onClick={toggleCollapsed}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            toggleCollapsed();
          }
        }}
        aria-expanded={!isCollapsed}
        aria-controls="suggestions-list-content"
        title={isCollapsed ? "Click to show suggestions" : "Click to hide suggestions"}
      >
        <div className="suggestions-header-left">
          <Sparkles size={12} className="sparkle-icon" aria-hidden="true" />
          <span className="suggestions-title">Suggested next steps</span>
          {isCollapsed && (
            <span className="suggestions-badge">{suggestions.length} available</span>
          )}
        </div>

        <button
          type="button"
          className="suggestions-dropdown-btn"
          onClick={(e) => {
            e.stopPropagation();
            toggleCollapsed();
          }}
          aria-expanded={!isCollapsed}
          aria-controls="suggestions-list-content"
          aria-label={isCollapsed ? "Show suggestions" : "Hide suggestions"}
          title={isCollapsed ? "Show suggestions" : "Hide suggestions"}
        >
          <ChevronDown
            size={12}
            className={`suggestions-dropdown-icon ${isCollapsed ? "is-collapsed" : "is-expanded"}`}
            aria-hidden="true"
          />
        </button>
      </div>

      {!isCollapsed && (
        <div className="suggestions-list" id="suggestions-list-content">
          {suggestions.map((s, idx) => (
            <button
              key={s.id || idx}
              type="button"
              className="suggestion-pill"
              disabled={disabled}
              onClick={() => onSelect(s.text)}
              style={{ animationDelay: `${idx * 50}ms` }}
              title={`Ask: "${s.text}"`}
            >
              {s.category && <span className="suggestion-category">{s.category}</span>}
              <span className="suggestion-text">{s.text}</span>
              <ArrowRight size={12} className="suggestion-arrow" aria-hidden="true" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
