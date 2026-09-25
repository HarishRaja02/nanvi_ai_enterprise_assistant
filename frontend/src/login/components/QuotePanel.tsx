import { useState } from "react";
import { QuoteItem } from "../types";
import { Sparkles } from "lucide-react";
import ribbonArt from "../assets/images/flowing_ribbon_art_1789978795531.jpg";
import { HERO_VIDEO_URL } from "../../lib/config";

const DEFAULT_QUOTES: QuoteItem[] = [
  {
    id: "quote-1",
    category: "A WISE QUOTE",
    headline: ["Get", "Everything", "You Want"],
    quote:
      "You can get everything you want if you work hard, trust the process, and stick to the plan.",
    author: "Unknown",
  },
  {
    id: "quote-2",
    category: "DAILY INSPIRATION",
    headline: ["Simplicity", "Is The Ultimate", "Sophistication"],
    quote:
      "Design is not just what it looks like and feels like. Design is how it works.",
    author: "Steve Jobs",
  },
  {
    id: "quote-3",
    category: "FOCUS & CLARITY",
    headline: ["Master", "Your Time,", "Own Your Life"],
    quote:
      "Success is the sum of small efforts, repeated day-in and day-out with unwavering conviction.",
    author: "Robert Collier",
  },
];

export function QuotePanel() {
  const [quoteIndex, setQuoteIndex] = useState(0);
  const current = DEFAULT_QUOTES[quoteIndex];

  const handleNextQuote = () => {
    setQuoteIndex((prev) => (prev + 1) % DEFAULT_QUOTES.length);
  };

  return (
    <div
      id="quote-panel"
      className="relative w-full h-full min-h-0 rounded-[22px] sm:rounded-[28px] border border-white/80 overflow-hidden flex flex-col justify-between p-6 sm:p-7 lg:p-9 text-white select-none shadow-2xl group"
    >
      {/* Background Video Animation of NANVI AI Robot Engine */}
      <video
        src={HERO_VIDEO_URL}
        autoPlay
        muted
        loop
        playsInline
        preload="metadata"
        poster={ribbonArt}
        className="absolute inset-0 w-full h-full object-cover object-center pointer-events-none transition-transform duration-700 ease-out group-hover:scale-105"
        aria-hidden="true"
      />

      {/* Atmospheric dark contrast gradients for pristine readability */}
      <div className="absolute inset-0 bg-gradient-to-b from-black/75 via-transparent to-black/90 pointer-events-none" />
      <div className="absolute inset-0 bg-radial from-transparent via-black/20 to-black/70 pointer-events-none" />

      {/* Top Bar: "A WISE QUOTE" with extending horizontal rule */}
      <div className="relative z-10 flex items-center justify-between gap-4">
        <div className="flex items-center gap-4 flex-1">
          <span className="text-[11px] tracking-[0.25em] font-medium text-white/90 uppercase whitespace-nowrap">
            {current.category}
          </span>
          <div className="h-[1px] bg-white/40 flex-1 max-w-[130px] sm:max-w-[190px]" />
        </div>

        {/* Subtle quote switcher button */}
        <button
          onClick={handleNextQuote}
          title="Shuffle inspiration"
          className="p-1.5 rounded-full text-white/50 hover:text-white hover:bg-white/10 transition-colors focus:outline-none"
          aria-label="Cycle quotes"
        >
          <Sparkles className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Bottom Content: High-contrast Serif Headline & Quote */}
      <div className="relative z-10 mt-auto pt-8 sm:pt-10">
        <h2 className="font-serif text-3xl sm:text-4xl lg:text-[40px] font-normal leading-[1.14] tracking-[-0.02em] text-white">
          {current.headline.map((line, idx) => (
            <span key={idx} className="block">
              {line}
            </span>
          ))}
        </h2>

        <p className="mt-3.5 text-xs sm:text-sm leading-relaxed text-neutral-300 font-normal max-w-sm text-balance">
          {current.quote}
        </p>
      </div>
    </div>
  );
}
