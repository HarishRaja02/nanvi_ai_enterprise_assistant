import React, { useEffect, useState } from "react";
import { Volume2 } from "lucide-react";

interface LiveCaptionBarProps {
  spokenText: string;
  isSpeaking: boolean;
  activeWordIndex?: number;
  className?: string;
}

export const LiveCaptionBar: React.FC<LiveCaptionBarProps> = ({
  spokenText,
  isSpeaking,
  className = "",
}) => {
  const [displayedWords, setDisplayedWords] = useState<string[]>([]);
  const [highlightIdx, setHighlightIdx] = useState<number>(0);

  useEffect(() => {
    if (!spokenText || !isSpeaking) {
      setDisplayedWords([]);
      setHighlightIdx(0);
      return;
    }

    const words = spokenText.split(/\s+/).filter(Boolean);
    setDisplayedWords(words);
    setHighlightIdx(0);

    // Approximate conversational pacing: ~240 words per minute -> ~250ms per word
    const interval = window.setInterval(() => {
      setHighlightIdx((prev) => {
        if (prev < words.length - 1) {
          return prev + 1;
        }
        clearInterval(interval);
        return prev;
      });
    }, 250);

    return () => clearInterval(interval);
  }, [spokenText, isSpeaking]);

  if (!isSpeaking || displayedWords.length === 0) {
    return null;
  }

  return (
    <div
      className={`live-caption-capsule flex items-center gap-3 px-4 py-2.5 rounded-full border border-cyan-500/25 bg-slate-950/85 backdrop-blur-xl shadow-2xl transition-all duration-300 ${className}`}
      role="region"
      aria-label="Live Spoken Captions"
      data-testid="live-caption-bar"
    >
      <div className="flex items-center gap-1.5 shrink-0 px-2 py-0.5 rounded-full bg-cyan-500/15 border border-cyan-500/30 text-cyan-400 text-[10px] font-bold tracking-wider uppercase">
        <Volume2 className="w-3 h-3 animate-pulse" />
        <span>Live</span>
      </div>

      <p className="text-xs sm:text-sm font-medium tracking-normal text-slate-200 truncate">
        {displayedWords.map((word, idx) => {
          const isSpoken = idx <= highlightIdx;
          const isCurrent = idx === highlightIdx;
          return (
            <span
              key={idx}
              className={`transition-colors duration-150 ${
                isCurrent
                  ? "text-cyan-300 font-semibold drop-shadow-[0_0_8px_rgba(6,182,212,0.6)]"
                  : isSpoken
                  ? "text-slate-100"
                  : "text-slate-500"
              }`}
            >
              {word}{" "}
            </span>
          );
        })}
      </p>
    </div>
  );
};
