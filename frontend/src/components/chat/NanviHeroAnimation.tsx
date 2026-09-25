import { useEffect, useRef, useState } from "react";
import { Play, Pause, Database, FileText, Mail, FolderGit2, BarChart3, Users, Sparkles } from "lucide-react";
import { HERO_VIDEO_URL, ICON_URL } from "../../lib/config";

interface NanviHeroAnimationProps {
  className?: string;
  onSelectSource?: (sourceName: string) => void;
}

const ORBITING_SOURCES = [
  { id: "docs", label: "Documents", icon: FileText, query: "Summarize latest enterprise policy documents" },
  { id: "emails", label: "Emails", icon: Mail, query: "Find high-priority emails regarding quarterly deliverables" },
  { id: "files", label: "Company Files", icon: FolderGit2, query: "Search company file archives for engineering architecture" },
  { id: "databases", label: "Databases", icon: Database, query: "Query production database for ledger balances and transactions" },
  { id: "analytics", label: "Analytics", icon: BarChart3, query: "Generate comparative analytics for operating EBITDA and revenue" },
  { id: "team", label: "Your Team", icon: Users, query: "Look up employee directory and department heads" },
];

const HOTSPOT_ELEMENTS = [
  {
    id: "docs",
    title: "Documents",
    subtitle: "PDF / Word / Cloud",
    top: "7.5%",
    left: "23.8%",
    width: "10.4%",
    height: "25.4%",
    query: "Review 2026 enterprise policy documents, compliance standards, and leave guidelines",
  },
  {
    id: "files",
    title: "Company Files",
    subtitle: "Shared Drives",
    top: "33.4%",
    left: "15.9%",
    width: "10.4%",
    height: "25.4%",
    query: "Inspect Project Phoenix cloud architecture, multi-region specs, and sprint milestones",
  },
  {
    id: "analytics",
    title: "Analytics",
    subtitle: "Reports & Insights",
    top: "58.8%",
    left: "22.6%",
    width: "10.4%",
    height: "25.4%",
    query: "Show me the August vs July revenue and expense breakdown with operating EBITDA and ledger balance",
  },
  {
    id: "emails",
    title: "Emails",
    subtitle: "Outlook / Gmail",
    top: "7.5%",
    left: "66.9%",
    width: "10.4%",
    height: "25.4%",
    query: "Search priority email threads and executive communication regarding deliverables",
  },
  {
    id: "databases",
    title: "Databases",
    subtitle: "SQL / PostgreSQL",
    top: "33.4%",
    left: "74.5%",
    width: "10.4%",
    height: "25.4%",
    query: "Query production database for ledger balances, SQL tables, and transaction records",
  },
  {
    id: "team",
    title: "Your Team",
    subtitle: "People & Processes",
    top: "58.8%",
    left: "67.9%",
    width: "10.4%",
    height: "25.4%",
    query: "Look up employee directory, department clearance levels, and team leads",
  },
];

export function NanviHeroAnimation({ className = "", onSelectSource }: NanviHeroAnimationProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [isPlaying, setIsPlaying] = useState(true);
  const [isLoaded, setIsLoaded] = useState(false);
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);
  const [hoveredElement, setHoveredElement] = useState<typeof HOTSPOT_ELEMENTS[0] | null>(null);

  useEffect(() => {
    // Respect user's reduced-motion preference
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    setPrefersReducedMotion(mediaQuery.matches);

    const handleMotionChange = (e: MediaQueryListEvent) => {
      setPrefersReducedMotion(e.matches);
      if (e.matches && videoRef.current) {
        videoRef.current.pause();
        setIsPlaying(false);
      }
    };
    mediaQuery.addEventListener("change", handleMotionChange);

    // Initial play if motion is not reduced
    if (!mediaQuery.matches && videoRef.current) {
      videoRef.current.play().catch(() => {
        // Autoplay may be blocked if unmuted or user hasn't interacted
        setIsPlaying(false);
      });
    }

    // IntersectionObserver: Pause when significantly out of viewport
    let observer: IntersectionObserver | null = null;
    if (containerRef.current) {
      observer = new IntersectionObserver(
        (entries) => {
          const entry = entries[0];
          if (!videoRef.current) return;

          if (entry.isIntersecting && !mediaQuery.matches) {
            videoRef.current.play().catch(() => {});
            setIsPlaying(true);
          } else {
            videoRef.current.pause();
            setIsPlaying(false);
          }
        },
        { threshold: 0.25 }
      );
      observer.observe(containerRef.current);
    }

    // Page Visibility: Pause when tab is hidden, resume when visible
    const handleVisibilityChange = () => {
      if (!videoRef.current) return;
      if (document.hidden) {
        videoRef.current.pause();
      } else if (!mediaQuery.matches) {
        videoRef.current.play().catch(() => {});
        setIsPlaying(true);
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      mediaQuery.removeEventListener("change", handleMotionChange);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      if (observer) {
        observer.disconnect();
      }
    };
  }, []);

  const togglePlayback = () => {
    if (!videoRef.current) return;
    if (isPlaying) {
      videoRef.current.pause();
      setIsPlaying(false);
    } else {
      videoRef.current.play().then(() => setIsPlaying(true)).catch(() => {});
    }
  };

  return (
    <div
      ref={containerRef}
      className={`nanvi-hero-stage ${className}`}
      aria-label="NANVI AI Enterprise Intelligence Animation"
    >
      {/* Outer ambient glow backlight */}
      <div className="nanvi-hero-glow-halo" aria-hidden="true" />

      {/* Main Glass Frame */}
      <div className="nanvi-hero-frame">
        {/* Top Status & Brand Header Bar inside Frame */}
        <div className="nanvi-hero-frame-bar">
          <div className="nanvi-hero-status-pill">
            <span className="nanvi-status-indicator-dot" aria-hidden="true">
              <span className="nanvi-status-ping" />
              <span className="nanvi-status-core" />
            </span>
            {hoveredElement ? (
              <span className="nanvi-status-label nanvi-status-active">
                CLICK TO QUERY: <strong className="nanvi-active-name">{hoveredElement.title.toUpperCase()}</strong> • {hoveredElement.subtitle}
              </span>
            ) : (
              <span className="nanvi-status-label">
                NANVI AI CORE • CLICK ANY ORBITING ELEMENT TO QUERY
              </span>
            )}
          </div>

          <div className="nanvi-hero-frame-actions">
            <button
              type="button"
              onClick={togglePlayback}
              className="nanvi-hero-ctrl-btn"
              title={isPlaying ? "Pause animation" : "Resume animation"}
              aria-label={isPlaying ? "Pause robot animation" : "Play robot animation"}
            >
              {isPlaying ? <Pause size={12} aria-hidden="true" /> : <Play size={12} aria-hidden="true" />}
              <span className="nanvi-ctrl-text">{isPlaying ? "Pause" : "Play"}</span>
            </button>
          </div>
        </div>

        {/* 16:9 Video Aspect Container */}
        <div className="nanvi-hero-video-box">
          <video
            ref={videoRef}
            src={HERO_VIDEO_URL}
            autoPlay={!prefersReducedMotion}
            muted
            loop
            playsInline
            preload="metadata"
            onLoadedData={() => setIsLoaded(true)}
            className={`nanvi-hero-video ${isLoaded ? "is-ready" : "is-loading"}`}
            aria-label="Animated NANVI AI robot with connected enterprise documents, databases, files, and teams orbiting"
          />

          {/* Vignette edge-blending overlay to seamlessly marry video edges into dark UI */}
          <div className="nanvi-hero-vignette" aria-hidden="true" />

          {/* Logo Mark Overlay exactly at the designated position */}
          <div className="nanvi-video-corner-logo" aria-hidden="true">
            <img src={ICON_URL} alt="Nanvi Brand Symbol" className="nanvi-video-n-icon" />
          </div>

          {/* Interactive Button Hotspots positioned directly over the elements in the video */}
          <div className="nanvi-video-hotspots-layer" role="toolbar" aria-label="Interactive enterprise source buttons">
            {HOTSPOT_ELEMENTS.map((elem) => (
              <button
                key={elem.id}
                type="button"
                className={`nanvi-hotspot-btn hotspot-${elem.id}`}
                style={{
                  top: elem.top,
                  left: elem.left,
                  width: elem.width,
                  height: elem.height,
                }}
                onMouseEnter={() => setHoveredElement(elem)}
                onMouseLeave={() => setHoveredElement(null)}
                onFocus={() => setHoveredElement(elem)}
                onBlur={() => setHoveredElement(null)}
                onClick={() => onSelectSource?.(elem.query)}
                aria-label={`Ask Nanvi AI about ${elem.title}: ${elem.query}`}
              >
                <span className="nanvi-hotspot-glow-border" aria-hidden="true" />
                <span className="nanvi-hotspot-action-hint" aria-hidden="true">
                  <span className="nanvi-hint-dot" />
                  <span className="nanvi-hint-text">Ask {elem.title}</span>
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Orbiting Sources Data Ribbon */}
        <div className="nanvi-hero-sources-banner">
          <div className="nanvi-sources-legend">
            <Sparkles size={11} className="nanvi-legend-icon" aria-hidden="true" />
            <span>ORBITING ENTERPRISE SYSTEMS:</span>
          </div>
          <div className="nanvi-sources-scroll-strip" role="list">
            {HOTSPOT_ELEMENTS.map((source) => (
              <button
                key={source.id}
                type="button"
                role="listitem"
                className={`nanvi-source-pill-btn ${hoveredElement?.id === source.id ? "is-highlighted" : ""}`}
                onMouseEnter={() => setHoveredElement(source)}
                onMouseLeave={() => setHoveredElement(null)}
                onClick={() => onSelectSource?.(source.query)}
                title={`Ask about ${source.title}`}
              >
                <span className="nanvi-source-name">{source.title}</span>
                <span className="nanvi-source-sub">({source.subtitle})</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
