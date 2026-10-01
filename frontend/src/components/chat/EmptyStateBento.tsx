import { useEffect, useRef, useState } from "react";
import type { FocusEvent, MouseEvent } from "react";
import { ArrowUpRight } from "lucide-react";
import type { PromptDef } from "../../lib/prompts";

const PROMPT_EXIT_MS = 360;
const PROMPT_ENTER_MS = 520;

interface Props {
  starters: PromptDef[];
  onPick: (query: string) => void;
  disabled?: boolean;
}

export function EmptyStateBento({ starters, onPick, disabled = false }: Props) {
  const [rotationIndex, setRotationIndex] = useState(0);
  const [dissolving, setDissolving] = useState(false);
  const [entering, setEntering] = useState(false);
  const paused = useRef(false);

  useEffect(() => {
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    if (reduceMotion || starters.length <= 4) return;

    let fadeStartTimer = 0;
    let swapTimer = 0;
    let enterTimer = 0;

    const scheduleNextPrompt = () => {
      fadeStartTimer = window.setTimeout(() => {
        if (paused.current) {
          scheduleNextPrompt();
          return;
        }

        setDissolving(true);
        swapTimer = window.setTimeout(() => {
          if (!paused.current) {
            setRotationIndex((index) => (index + 1) % starters.length);
            setEntering(true);
            enterTimer = window.setTimeout(() => setEntering(false), PROMPT_ENTER_MS + 180);
          }
          setDissolving(false);
          scheduleNextPrompt();
        }, PROMPT_EXIT_MS);
      }, 2500);
    };

    scheduleNextPrompt();

    return () => {
      window.clearTimeout(fadeStartTimer);
      window.clearTimeout(swapTimer);
      window.clearTimeout(enterTimer);
    };
  }, [starters.length]);

  const pauseOnFocusLeave = (event: FocusEvent<HTMLDivElement>) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) paused.current = false;
  };

  const pauseOnPointerLeave = (event: MouseEvent<HTMLDivElement>) => {
    if (!event.currentTarget.matches(":focus-within")) paused.current = false;
  };

  return (
    <section className="empty-workspace-view" aria-labelledby="empty-chat-title">
      <div className="hero-header-section">
        <h2 id="empty-chat-title" className="hero-greeting">How can I help?</h2>
        <p className="hero-subtitle">
          Ask about company files, email, employees, projects, or business data.
        </p>
      </div>

      {starters.length > 0 && (
        <section className="welcome-prompts" aria-label="Suggested questions">
          <p>Try a question</p>
          <div
            className="welcome-prompt-list"
            onMouseEnter={() => { paused.current = true; }}
            onMouseLeave={pauseOnPointerLeave}
            onFocus={() => { paused.current = true; }}
            onBlur={pauseOnFocusLeave}
          >
            {starters.slice(0, 4).map((_, slot) => {
              const starter = starters[(rotationIndex + slot) % starters.length];
              return (
              <button
                key={`${slot}-${starter.prompt}`}
                type="button"
                className={`welcome-prompt${dissolving ? " is-dissolving" : ""}${entering ? " is-entering" : ""}`}
                style={{ animationDelay: entering ? `${slot * 55}ms` : undefined }}
                disabled={disabled}
                onClick={() => onPick(starter.prompt)}
              >
                <span>{starter.prompt}</span>
                <ArrowUpRight className="welcome-prompt-arrow" size={18} aria-hidden="true" />
              </button>
              );
            })}
          </div>
        </section>
      )}
    </section>
  );
}
