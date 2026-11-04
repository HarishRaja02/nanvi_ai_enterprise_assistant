import React, { useState } from "react";
import {
  Download,
  ExternalLink,
  Laptop,
  Globe,
  FileText,
  Shield,
  ShieldCheck,
  CheckCircle2,
  Folder,
  Search,
  ArrowRight,
  Sparkles,
  FileSpreadsheet,
  Check,
  Copy,
  Eye,
  Layers,
  Lock,
  Cpu,
  Mic,
  Server,
} from "lucide-react";
import { LOGO_URL } from "../../lib/config";
import { useToast } from "../ui/Toast";

interface Props {
  onLaunchWebApp: () => void;
}

interface SampleQuery {
  title: string;
  query: string;
  fileName: string;
  filePath: string;
  fileType: string;
  summary: string;
  details: { label: string; value: string }[];
}

const SAMPLE_QUERIES: SampleQuery[] = [
  {
    title: "Vendor Invoice Search",
    query: "Sri Ganesh ReadyMix find this vendor in invoice",
    fileName: "invoice_register.csv",
    filePath: "C:\\CompanyData\\08_Finance\\Invoices\\invoice_register.csv",
    fileType: "CSV Spreadsheet",
    summary: "Found 1 matching invoice document in Local Storage for vendor 'Sri Ganesh ReadyMix'.",
    details: [
      { label: "Invoice No", value: "INV-2024-8841" },
      { label: "Vendor", value: "Sri Ganesh ReadyMix" },
      { label: "Amount Due", value: "₹4,85,000" },
      { label: "Payment Status", value: "Approved / Pending Release" },
    ],
  },
  {
    title: "Payment Aging Audit",
    query: "Show aging breakdown for pending supplier payments",
    fileName: "invoice_aging.xlsx",
    filePath: "C:\\CompanyData\\08_Finance\\Invoices\\invoice_aging.xlsx",
    fileType: "Excel Workbook",
    summary: "Identified 4 overdue invoices past 60 days in Bridge Construction finance records.",
    details: [
      { label: "Total Overdue", value: "₹18,42,500" },
      { label: "Over 90 Days", value: "2 Suppliers (₹7,15,000)" },
      { label: "Action", value: "Priority review required by Accounts" },
      { label: "Department", value: "Finance & Accounts" },
    ],
  },
  {
    title: "Contract Specifications",
    query: "Summarize contract terms and warranty liabilities in bridge agreement",
    fileName: "Mock_Contract_Agreement.pdf",
    filePath: "C:\\CompanyData\\10_Contracts\\Mock_Contract_Agreement.pdf",
    fileType: "PDF Document",
    summary: "Verified 24-month defect liability period and 5% retention guarantee clause.",
    details: [
      { label: "Project", value: "National Highway Bridge Section 4" },
      { label: "Liability Term", value: "24 months post-commissioning" },
      { label: "Bank Guarantee", value: "5% Performance Security valid to 2026" },
      { label: "Arbitration", value: "New Delhi Jurisdiction" },
    ],
  },
];

export function LandingPage({ onLaunchWebApp }: Props) {
  const notify = useToast();
  const [downloading, setDownloading] = useState(false);
  const [downloadFormat, setDownloadFormat] = useState<"bat" | "zip">("bat");
  const [activeQueryIdx, setActiveQueryIdx] = useState(0);
  const [copiedPath, setCopiedPath] = useState(false);
  const [previewExpanded, setPreviewExpanded] = useState(false);

  const activeSample = SAMPLE_QUERIES[activeQueryIdx];

  const handleDownload = async (format: "bat" | "zip" = "bat") => {
    setDownloading(true);
    try {
      const isDesktopOrigin =
        typeof window !== "undefined" &&
        (window.location.protocol === "file:" || Boolean((window as any).electronAPI?.isDesktop));
      const base = isDesktopOrigin ? "http://127.0.0.1:8000/api" : "/api";

      const url = `${base}/local-agent/download?format=${format}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error("Download request failed");

      const blob = await res.blob();
      const objUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objUrl;
      a.download = format === "zip" ? "Nanvi_Windows_Agent.zip" : "Nanvi_Assistant.bat";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => window.URL.revokeObjectURL(objUrl), 5000);

      notify(
        `Downloaded ${format === "zip" ? "Nanvi_Windows_Agent.zip" : "Nanvi_Assistant.bat"}! Click to run on your Windows PC.`,
        "success"
      );
    } catch {
      // Direct browser fallback
      window.location.href = `/api/local-agent/download?format=${format}`;
      notify("Download initiated.", "info");
    } finally {
      setDownloading(false);
    }
  };

  const handleCopyMockPath = async () => {
    try {
      await navigator.clipboard.writeText(activeSample.filePath);
      setCopiedPath(true);
      notify("Copied file path to clipboard", "success");
      setTimeout(() => setCopiedPath(false), 2000);
    } catch {
      notify("Could not copy path", "danger");
    }
  };

  return (
    <div className="landing-page">
      <div className="landing-bg-mesh" aria-hidden="true" />

      {/* ── Top Navigation Bar ────────────────────────────────────────── */}
      <header className="landing-nav" role="banner">
        <div className="landing-nav-inner">
          <div className="landing-brand" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}>
            <img src={LOGO_URL} alt="Nanvi Logo" className="landing-brand-logo" />
            <div className="landing-brand-text">
              <span className="landing-brand-name">Nanvi AI</span>
              <span className="landing-brand-tag">Enterprise Assistant</span>
            </div>
          </div>

          <nav className="landing-nav-links" aria-label="Main Navigation">
            <a href="#capabilities" className="landing-nav-link">
              What We Do
            </a>
            <a href="#architecture" className="landing-nav-link">
              Web & Desktop
            </a>
            <a href="#how-it-works" className="landing-nav-link">
              How It Works
            </a>
            <a href="#downloads" className="landing-nav-link">
              Download
            </a>
          </nav>

          <div className="landing-nav-actions">
            <button
              type="button"
              className="btn-landing-secondary"
              onClick={() => handleDownload("bat")}
              title="Download Windows Local Runner"
              style={{ padding: "8px 16px", fontSize: "13.5px" }}
            >
              <Download size={14} />
              <span>Download for Windows</span>
            </button>
            <button
              type="button"
              className="btn-landing-primary"
              onClick={onLaunchWebApp}
              title="Launch Web Assistant in Browser"
              style={{ padding: "8px 18px", fontSize: "13.5px" }}
            >
              <span>Launch Web Assistant</span>
              <ArrowRight size={14} />
            </button>
          </div>
        </div>
      </header>

      {/* ── Hero Section ──────────────────────────────────────────────── */}
      <section className="landing-hero" aria-label="Hero Introduction">
        <div className="landing-pill">
          <Sparkles size={14} className="text-green-600" />
          <span>Hybrid Architecture • Zero Confidential Cloud Leak • Windows Local PC & Web Service</span>
        </div>

        <h1 className="landing-hero-title">
          The Secure Enterprise AI Assistant for <span className="highlight-teal">Corporate Documents</span>,{" "}
          <span className="highlight-green">Invoices</span> & Operations
        </h1>

        <p className="landing-hero-subtitle">
          Instantly query vendor records, analyze financial ledgers, audit complex contracts, and search across thousands of
          local business documents — powered by in-memory ephemeral previews, native desktop launching, and zero cloud retention.
        </p>

        <div className="landing-hero-ctas">
          <button
            type="button"
            className="btn-landing-primary"
            onClick={() => handleDownload("bat")}
            disabled={downloading}
            style={{ fontSize: "16px", padding: "14px 28px" }}
          >
            <Download size={18} />
            <span>{downloading ? "Preparing Download..." : "Download for Windows (.bat)"}</span>
          </button>

          <button
            type="button"
            className="btn-landing-secondary"
            onClick={onLaunchWebApp}
            style={{ fontSize: "16px", padding: "14px 28px" }}
          >
            <Globe size={18} />
            <span>Launch Web Assistant</span>
          </button>
        </div>

        <div className="landing-hero-meta">
          <span>⚡ Windows 10 & 11 Compatible</span>
          <span>•</span>
          <span>🔒 1-Click Self-Contained Runner</span>
          <span>•</span>
          <span>🌐 Zero-Install Web Service Available</span>
        </div>

        {/* ── Badges Strip ────────────────────────────────────────────── */}
        <div className="landing-badges-strip">
          <div className="landing-badge-item">
            <Lock size={16} />
            <span>Ephemeral RAM Previews</span>
          </div>
          <div className="landing-badge-item">
            <Laptop size={16} />
            <span>Local PC Hard Drive Indexing</span>
          </div>
          <div className="landing-badge-item">
            <ShieldCheck size={16} />
            <span>Role-Based Access (RBAC)</span>
          </div>
          <div className="landing-badge-item">
            <Mic size={16} />
            <span>Neural Voice Core Integration</span>
          </div>
        </div>

        {/* ── Interactive Live Product Showcase Mockup ────────────────── */}
        <div className="landing-mockup-wrapper" aria-label="Product Interface Mockup">
          <div className="landing-mockup-topbar">
            <div className="mockup-traffic-lights">
              <span className="mockup-light red" />
              <span className="mockup-light yellow" />
              <span className="mockup-light green" />
            </div>
            <div className="mockup-search-input">
              <Search size={14} className="text-slate-400" />
              <span>{activeSample.query}</span>
            </div>
            <div style={{ display: "flex", gap: "6px" }}>
              <span className="mockup-badge-verified">
                <CheckCircle2 size={12} /> Local Storage Verified
              </span>
            </div>
          </div>

          <div className="mockup-body">
            {/* Query selector pills */}
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
              <span style={{ fontSize: "12px", fontWeight: 700, color: "#64748b", textTransform: "uppercase" }}>
                Try Enterprise Sample Queries:
              </span>
              {SAMPLE_QUERIES.map((sq, i) => (
                <button
                  key={sq.title}
                  type="button"
                  onClick={() => {
                    setActiveQueryIdx(i);
                    setPreviewExpanded(false);
                  }}
                  style={{
                    background: activeQueryIdx === i ? "#006583" : "#f1f5f9",
                    color: activeQueryIdx === i ? "#ffffff" : "#334155",
                    border: "1px solid",
                    borderColor: activeQueryIdx === i ? "#004d63" : "#cbd5e1",
                    padding: "4px 12px",
                    borderRadius: "6px",
                    fontSize: "12.5px",
                    fontWeight: 600,
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                  }}
                >
                  {sq.title}
                </button>
              ))}
            </div>

            {/* Simulated User Question */}
            <div className="mockup-bubble-user">{activeSample.query}</div>

            {/* Simulated Assistant Answer */}
            <div className="mockup-bubble-assistant">
              <div className="mockup-header-row">
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <div
                    style={{
                      width: "24px",
                      height: "24px",
                      borderRadius: "4px",
                      background: "#006583",
                      color: "#fff",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: "12px",
                      fontWeight: 700,
                    }}
                  >
                    N
                  </div>
                  <strong style={{ fontSize: "14px", color: "#0f172a" }}>Nanvi Assistant</strong>
                  <span
                    style={{
                      background: "#e0f2fe",
                      color: "#0369a1",
                      fontSize: "11px",
                      padding: "2px 6px",
                      borderRadius: "4px",
                      fontWeight: 600,
                    }}
                  >
                    Document Search
                  </span>
                </div>
                <span style={{ fontSize: "12px", color: "#64748b" }}>Found in local indexed folders</span>
              </div>

              <p style={{ margin: "0 0 14px", fontSize: "14px", color: "#334155", lineHeight: 1.5 }}>
                {activeSample.summary}
              </p>

              {/* File Results Interactive Table Mockup */}
              <div
                style={{
                  background: "#ffffff",
                  border: "1px solid #cbd5e1",
                  borderRadius: "8px",
                  overflow: "hidden",
                  boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
                }}
              >
                <div
                  style={{
                    background: "#f8fafc",
                    padding: "8px 12px",
                    borderBottom: "1px solid #e2e8f0",
                    fontSize: "12px",
                    fontWeight: 600,
                    color: "#64748b",
                    display: "flex",
                    justifyContent: "space-between",
                  }}
                >
                  <span>1 MATCHING COMPANY DOCUMENT</span>
                  <span>🔒 In-Memory Ephemeral RAM Preview</span>
                </div>
                <div
                  style={{
                    padding: "12px 14px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    flexWrap: "wrap",
                    gap: "12px",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                    <FileSpreadsheet className="text-teal-700" size={20} />
                    <div>
                      <div style={{ fontWeight: 700, fontSize: "14px", color: "#0f172a" }}>
                        {activeSample.fileName}
                      </div>
                      <code style={{ fontSize: "11.5px", color: "#0284c7" }}>{activeSample.filePath}</code>
                    </div>
                  </div>

                  <div style={{ display: "flex", gap: "6px" }}>
                    <button
                      type="button"
                      onClick={handleCopyMockPath}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "5px",
                        background: "#f1f5f9",
                        border: "1px solid #cbd5e1",
                        borderRadius: "6px",
                        padding: "6px 10px",
                        fontSize: "12px",
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                    >
                      {copiedPath ? <Check size={12} className="text-green-600" /> : <Copy size={12} />}
                      <span>{copiedPath ? "Copied!" : "Copy Path"}</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setPreviewExpanded(!previewExpanded)}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "5px",
                        background: previewExpanded ? "#e0f2fe" : "#ffffff",
                        border: "1px solid #cbd5e1",
                        borderRadius: "6px",
                        padding: "6px 12px",
                        fontSize: "12px",
                        fontWeight: 600,
                        cursor: "pointer",
                        color: "#0369a1",
                      }}
                    >
                      <Eye size={12} />
                      <span>{previewExpanded ? "Hide Preview" : "Preview"}</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        handleCopyMockPath();
                        notify(`Opened ${activeSample.fileName} in Windows default application`, "success");
                      }}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "5px",
                        background: "#006583",
                        border: "1px solid #004d63",
                        color: "#ffffff",
                        borderRadius: "6px",
                        padding: "6px 12px",
                        fontSize: "12px",
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                    >
                      <ExternalLink size={12} />
                      <span>Open in Excel/App</span>
                    </button>
                  </div>
                </div>

                {/* Simulated In-Memory Ephemeral Preview Drawer */}
                {previewExpanded && (
                  <div
                    style={{
                      borderTop: "1px solid #e2e8f0",
                      background: "#f0fdf4",
                      padding: "14px 16px",
                      animation: "fadeIn 0.2s ease-in-out",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        marginBottom: "10px",
                      }}
                    >
                      <span style={{ fontSize: "12px", fontWeight: 700, color: "#166534" }}>
                        🔒 In-Memory Ephemeral Data View (Decoded in Browser RAM):
                      </span>
                      <span style={{ fontSize: "11px", color: "#64748b" }}>Zero Cloud Persistence</span>
                    </div>

                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                        gap: "8px",
                      }}
                    >
                      {activeSample.details.map((d) => (
                        <div
                          key={d.label}
                          style={{
                            background: "#ffffff",
                            padding: "8px 10px",
                            borderRadius: "6px",
                            border: "1px solid #cbd5e1",
                          }}
                        >
                          <div style={{ fontSize: "11px", color: "#64748b", fontWeight: 600 }}>{d.label}</div>
                          <div style={{ fontSize: "13px", fontWeight: 700, color: "#0f172a" }}>{d.value}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Section: What We Do & What Is The Use Of It ───────────────── */}
      <section id="capabilities" className="landing-section" aria-label="Capabilities">
        <div className="landing-section-head">
          <span className="landing-eyebrow">Enterprise Value Proposition</span>
          <h2 className="landing-section-title">What Nanvi AI Does & What You Use It For</h2>
          <p className="landing-section-sub">
            Traditional corporate search forces employees to browse complex network drives and read endless files.
            Nanvi AI bridges local business folders and enterprise cloud intelligence into a single conversation.
          </p>
        </div>

        <div className="landing-grid-4">
          <div className="landing-card">
            <div className="landing-card-icon">
              <FileSpreadsheet size={22} />
            </div>
            <h3 className="landing-card-title">Invoice & Ledger Auditing</h3>
            <p className="landing-card-desc">
              Instantly track invoices, vendor dues, tax amounts, and aging cycles across thousands of spreadsheet and CSV files
              without manual lookup.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon">
              <Folder size={22} />
            </div>
            <h3 className="landing-card-title">Private Local PC Indexing</h3>
            <p className="landing-card-desc">
              Connect your local Windows folders (`CompanyData`, `Invoices`, network drives). Indexing runs locally so confidential
              files never leave your computer.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon">
              <Eye size={22} />
            </div>
            <h3 className="landing-card-title">In-Memory Ephemeral Previews</h3>
            <p className="landing-card-desc">
              Inspect full spreadsheet tables, contracts, and PDFs directly in browser memory. No temporary copies are saved on cloud
              servers.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon">
              <ExternalLink size={22} />
            </div>
            <h3 className="landing-card-title">Native Windows App Launching</h3>
            <p className="landing-card-desc">
              One-click opening launches documents directly in native Windows apps (Excel, Word, Notepad, Acrobat) and copies the path
              to your clipboard.
            </p>
          </div>
        </div>
      </section>

      {/* ── Section: Dual Architecture (Web vs Local App) ─────────────── */}
      <section id="architecture" className="landing-section" style={{ background: "#f1f5f9", borderRadius: "20px" }}>
        <div className="landing-section-head">
          <span className="landing-eyebrow">Deployment Flexibility</span>
          <h2 className="landing-section-title">Both Web Service & Local Application</h2>
          <p className="landing-section-sub">
            Nanvi AI gives you the best of both worlds: a private Windows local application for secure workstation files,
            plus a modern cloud web service for browser access anywhere.
          </p>
        </div>

        <div className="landing-arch-grid">
          {/* Local Windows Application Card */}
          <div className="arch-card featured">
            <span className="arch-badge-ribbon">Local PC Workstation</span>
            <div className="arch-card-header">
              <div className="arch-icon">
                <Laptop size={26} />
              </div>
              <h3 className="arch-card-title">Local Windows Application</h3>
              <p className="arch-card-desc">
                Ideal for finance, engineering, and procurement workstations with sensitive local hard drive storage.
              </p>
            </div>

            <ul className="arch-feature-list">
              <li className="arch-feature-item">
                <CheckCircle2 size={16} />
                <span>Runs directly on Windows 10 & 11 via 1-click batch runner or Electron app</span>
              </li>
              <li className="arch-feature-item">
                <CheckCircle2 size={16} />
                <span>Connects to local folders (`C:\CompanyData`, `Invoices`, mapped drives)</span>
              </li>
              <li className="arch-feature-item">
                <CheckCircle2 size={16} />
                <span>1-click file opening launches Microsoft Excel, Word, Acrobat, or Notepad</span>
              </li>
              <li className="arch-feature-item">
                <CheckCircle2 size={16} />
                <span>Zero confidential file uploads — indexing and hashing stay on your PC</span>
              </li>
              <li className="arch-feature-item">
                <CheckCircle2 size={16} />
                <span>Automatic pairing with cloud web assistant via secure token</span>
              </li>
            </ul>

            <button
              type="button"
              className="btn-landing-primary"
              onClick={() => handleDownload("bat")}
              disabled={downloading}
              style={{ width: "100%", justifyContent: "center" }}
            >
              <Download size={16} />
              <span>Download for Windows (.bat)</span>
            </button>
          </div>

          {/* Cloud Web Service Card */}
          <div className="arch-card">
            <span className="arch-badge-ribbon" style={{ background: "#eff6ff", color: "#1e40af", borderColor: "#bfdbfe" }}>
              Cloud Web Service
            </span>
            <div className="arch-card-header">
              <div className="arch-icon" style={{ background: "#eff6ff", color: "#2563eb" }}>
                <Globe size={26} />
              </div>
              <h3 className="arch-card-title">Enterprise Cloud Web Portal</h3>
              <p className="arch-card-desc">
                Ideal for remote executives, project managers, and mobile reviews with zero local setup needed.
              </p>
            </div>

            <ul className="arch-feature-list">
              <li className="arch-feature-item">
                <CheckCircle2 size={16} />
                <span>Accessible on any modern web browser at your enterprise URL</span>
              </li>
              <li className="arch-feature-item">
                <CheckCircle2 size={16} />
                <span>Role-based access control (Supervisor, Project Engineer, Employee, Admin)</span>
              </li>
              <li className="arch-feature-item">
                <CheckCircle2 size={16} />
                <span>Live agent status monitoring and real-time synchronization</span>
              </li>
              <li className="arch-feature-item">
                <CheckCircle2 size={16} />
                <span>Comprehensive conversation history and audit log exports</span>
              </li>
              <li className="arch-feature-item">
                <CheckCircle2 size={16} />
                <span>Zero installation required — just sign in and ask</span>
              </li>
            </ul>

            <button
              type="button"
              className="btn-landing-secondary"
              onClick={onLaunchWebApp}
              style={{ width: "100%", justifyContent: "center" }}
            >
              <ExternalLink size={16} />
              <span>Launch Web Service</span>
            </button>
          </div>
        </div>
      </section>

      {/* ── Section: How It Works ─────────────────────────────────────── */}
      <section id="how-it-works" className="landing-section" aria-label="How It Works">
        <div className="landing-section-head">
          <span className="landing-eyebrow">Simple Workflow</span>
          <h2 className="landing-section-title">Up and Running in 3 Steps</h2>
          <p className="landing-section-sub">
            No database migration, no complex installations, and no command-line hassle.
          </p>
        </div>

        <div className="landing-steps-row">
          <div className="landing-step-card">
            <span className="step-num-badge">1</span>
            <h3 className="step-card-title">Download & Run</h3>
            <p className="step-card-desc">
              Download <strong>Nanvi_Assistant.bat</strong> and double-click to run on your Windows PC.
              The application window and terminal assistant appear immediately.
            </p>
          </div>

          <div className="landing-step-card">
            <span className="step-num-badge">2</span>
            <h3 className="step-card-title">Connect Business Folder</h3>
            <p className="step-card-desc">
              Point to your local documents folder (e.g. <code>companydata_bridge_construction</code> or <code>C:\CompanyData</code>).
              Nanvi indexes and hashes your records securely.
            </p>
          </div>

          <div className="landing-step-card">
            <span className="step-num-badge">3</span>
            <h3 className="step-card-title">Ask Text or Voice Queries</h3>
            <p className="step-card-desc">
              Ask questions like <em>"Find unpaid invoices for Sri Ganesh ReadyMix"</em>.
              Get exact answers, verified citations, in-memory table previews, and 1-click desktop opening.
            </p>
          </div>
        </div>
      </section>

      {/* ── Section: Download Center & Cloud Web Access ───────────────── */}
      <section id="downloads" className="landing-section" aria-label="Download Center">
        <div className="download-center-banner">
          <div className="download-banner-left">
            <h2>Get Started with Nanvi AI Enterprise Assistant</h2>
            <p>
              Download the 1-click Windows package to query your local folders, or launch the cloud web service directly in your browser.
            </p>

            <div className="download-banner-actions">
              <button
                type="button"
                className="btn-landing-primary"
                onClick={() => handleDownload(downloadFormat)}
                disabled={downloading}
                style={{ background: "#ffffff", color: "#0f172a !important" }}
              >
                <Download size={18} className="text-teal-800" />
                <span style={{ color: "#0f172a" }}>
                  {downloading ? "Downloading..." : `Download for Windows (.${downloadFormat})`}
                </span>
              </button>

              <button
                type="button"
                className="btn-landing-secondary"
                onClick={onLaunchWebApp}
                style={{ background: "rgba(255, 255, 255, 0.15)", color: "#ffffff !important", borderColor: "rgba(255, 255, 255, 0.3)" }}
              >
                <Globe size={18} />
                <span style={{ color: "#ffffff" }}>Launch Web Assistant</span>
              </button>
            </div>

            <div style={{ marginTop: "16px", fontSize: "13px", color: "#cbd5e1", display: "flex", gap: "14px", alignItems: "center" }}>
              <span>Download format:</span>
              <label style={{ display: "inline-flex", alignItems: "center", gap: "4px", cursor: "pointer" }}>
                <input
                  type="radio"
                  name="downloadFormat"
                  checked={downloadFormat === "bat"}
                  onChange={() => setDownloadFormat("bat")}
                />
                1-Click BAT (Recommended)
              </label>
              <label style={{ display: "inline-flex", alignItems: "center", gap: "4px", cursor: "pointer" }}>
                <input
                  type="radio"
                  name="downloadFormat"
                  checked={downloadFormat === "zip"}
                  onChange={() => setDownloadFormat("zip")}
                />
                ZIP Archive
              </label>
            </div>
          </div>

          <div className="download-banner-right">
            <h4>Quick Launch Instructions:</h4>
            <ul className="download-steps-mini">
              <li>
                <CheckCircle2 size={16} className="text-green-400" />
                <span>1. Click Download to save <code>Nanvi_Assistant.bat</code></span>
              </li>
              <li>
                <CheckCircle2 size={16} className="text-green-400" />
                <span>2. Run the file on your Windows computer</span>
              </li>
              <li>
                <CheckCircle2 size={16} className="text-green-400" />
                <span>3. Nanvi Assistant automatically launches in your browser</span>
              </li>
              <li>
                <CheckCircle2 size={16} className="text-green-400" />
                <span>4. Select your folder and start querying immediately</span>
              </li>
            </ul>
          </div>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────────────────────── */}
      <footer className="landing-footer" role="contentinfo">
        <div className="landing-footer-inner">
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <img src={LOGO_URL} alt="Nanvi Logo" style={{ height: "24px", width: "auto" }} />
            <span style={{ fontWeight: 700, color: "#0f172a" }}>Nanvi AI Enterprise Assistant</span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "18px" }}>
            <span>🔒 Enterprise Grade</span>
            <span>•</span>
            <span>⚡ Windows 10/11 & Cloud</span>
            <span>•</span>
            <button
              type="button"
              onClick={onLaunchWebApp}
              style={{ background: "none", border: "none", color: "#006583", fontWeight: 600, cursor: "pointer", textDecoration: "underline" }}
            >
              Sign In to Web Portal
            </button>
          </div>

          <div>
            <span>© {new Date().getFullYear()} Nanvi AI. All rights reserved.</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default LandingPage;

