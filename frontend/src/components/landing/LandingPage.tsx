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
  Store,
  MessageSquare,
  BarChart3,
  Users,
  Mail,
  Database,
  AlertTriangle,
  Zap,
  BookOpen,
  Settings,
  Activity,
  FolderSearch,
  BrainCircuit,
  HardDrive,
  CloudOff,
  MonitorSmartphone,
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
    title: "Invoice Search",
    query: "Find all unpaid invoices for Sri Ganesh ReadyMix above ₹2 lakhs",
    fileName: "invoice_register.csv",
    filePath: "C:\\CompanyData\\08_Finance\\Invoices\\invoice_register.csv",
    fileType: "CSV Spreadsheet",
    summary: "Found 3 matching invoices for vendor 'Sri Ganesh ReadyMix' with outstanding amount above ₹2,00,000.",
    details: [
      { label: "Invoices Found", value: "3 records" },
      { label: "Total Outstanding", value: "₹8,45,000" },
      { label: "Oldest Due Date", value: "18-Sep-2024" },
      { label: "Payment Status", value: "Pending Release" },
    ],
  },
  {
    title: "Contract Audit",
    query: "What are the warranty and liability terms in the highway bridge contract?",
    fileName: "Bridge_Contract_Agreement.pdf",
    filePath: "C:\\CompanyData\\10_Contracts\\Bridge_Contract_Agreement.pdf",
    fileType: "PDF Document",
    summary: "Extracted key contract clauses: 24-month defect liability, 5% performance security, and arbitration terms.",
    details: [
      { label: "Liability Period", value: "24 months post-handover" },
      { label: "Performance Guarantee", value: "5% Bank Guarantee" },
      { label: "Penalty Clause", value: "0.5% per week of delay" },
      { label: "Jurisdiction", value: "High Court, Chennai" },
    ],
  },
  {
    title: "Payment Report",
    query: "Generate aging report for all supplier payments overdue by 60+ days",
    fileName: "supplier_payments.xlsx",
    filePath: "C:\\CompanyData\\08_Finance\\Payments\\supplier_payments.xlsx",
    fileType: "Excel Workbook",
    summary: "Generated aging breakdown: 4 suppliers with payments overdue beyond 60 days totaling ₹18.4L.",
    details: [
      { label: "60-90 Days Overdue", value: "₹11,27,500 (2 vendors)" },
      { label: "90+ Days Overdue", value: "₹7,15,000 (2 vendors)" },
      { label: "Action Required", value: "Immediate escalation" },
      { label: "Department", value: "Accounts Payable" },
    ],
  },
];

// Microsoft Store link for Nanvi AI Enterprise Assistant
const MS_STORE_URL = "https://apps.microsoft.com/detail/9NZMM1MV9XX4?hl=en-us&gl=IN&ocid=pdpshare";

export function LandingPage({ onLaunchWebApp }: Props) {
  const notify = useToast();
  const [downloading, setDownloading] = useState(false);
  const [downloadFormat, setDownloadFormat] = useState<"exe" | "bat" | "zip">("exe");
  const [activeQueryIdx, setActiveQueryIdx] = useState(0);
  const [copiedPath, setCopiedPath] = useState(false);
  const [previewExpanded, setPreviewExpanded] = useState(false);
  const [showExeWarning, setShowExeWarning] = useState(false);

  const activeSample = SAMPLE_QUERIES[activeQueryIdx];

  const handleDownload = async (format: "exe" | "bat" | "zip" = "exe") => {
    setDownloading(true);
    try {
      const isDesktopOrigin =
        typeof window !== "undefined" &&
        (window.location.protocol === "file:" || Boolean((window as any).electronAPI?.isDesktop));
      const base = isDesktopOrigin
        ? "http://127.0.0.1:8000/api"
        : (import.meta as any).env?.VITE_API_BASE_URL || "/api";
      const url = `${base}/local-agent/download?format=${format}`;

      if (format === "exe") {
        const a = document.createElement("a");
        a.href = url;
        a.download = "Nanvi AI Assistant-Setup-0.1.1.exe";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        notify(
          "Downloading Nanvi AI Assistant Setup (.exe)... Note: Windows Smart App Control may block the installer since it is not code-signed. For a hassle-free install, use the Microsoft Store version.",
          "success"
        );
        return;
      }

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
            <a href="#features" className="landing-nav-link">
              Features
            </a>
            <a href="#how-it-works" className="landing-nav-link">
              How It Works
            </a>
            <a href="#architecture" className="landing-nav-link">
              Web & Desktop
            </a>
            <a href="#downloads" className="landing-nav-link">
              Get the App
            </a>
          </nav>

          <div className="landing-nav-actions">
            <a
              href={MS_STORE_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-landing-primary"
              title="Get Nanvi AI from Microsoft Store"
              style={{ padding: "8px 16px", fontSize: "13.5px" }}
            >
              <Store size={14} />
              <span>Get from Microsoft Store</span>
            </a>
            <button
              type="button"
              className="btn-landing-secondary"
              onClick={onLaunchWebApp}
              title="Launch Web Assistant in Browser"
              style={{ padding: "8px 18px", fontSize: "13.5px" }}
            >
              <span>Launch Web App</span>
              <ArrowRight size={14} />
            </button>
          </div>
        </div>
      </header>

      {/* ── Hero Section ──────────────────────────────────────────────── */}
      <section className="landing-hero" aria-label="Hero Introduction">
        <div className="landing-pill">
          <ShieldCheck size={14} className="text-green-600" />
          <span>Available on Microsoft Store & Web — No Installation Hassle</span>
        </div>

        <h1 className="landing-hero-title">
          Ask Questions About Your <span className="highlight-teal">Business Documents</span>,{" "}
          <span className="highlight-green">Invoices</span> & Company Data
        </h1>

        <p className="landing-hero-subtitle">
          Nanvi AI reads your local files — invoices, contracts, spreadsheets, PDFs — and answers
          your questions in plain English. No manual searching. No uploading to cloud servers.
          Your documents stay on your computer.
        </p>

        <div className="landing-hero-ctas">
          {/* Microsoft Store - PRIMARY */}
          <a
            href={MS_STORE_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-landing-primary"
            style={{ fontSize: "16px", padding: "14px 28px" }}
          >
            <Store size={18} />
            <span>Get it from Microsoft Store</span>
          </a>

          <button
            type="button"
            className="btn-landing-secondary"
            onClick={onLaunchWebApp}
            style={{ fontSize: "16px", padding: "14px 28px" }}
          >
            <Globe size={18} />
            <span>Open Web App (No Install)</span>
          </button>
        </div>

        <div className="landing-hero-meta">
          <span>✅ Microsoft Store Verified — Installs Without Warnings</span>
          <span>•</span>
          <span>🌐 Web Version Works in Any Browser</span>
          <span>•</span>
          <span>🔒 Your Files Never Leave Your Computer</span>
        </div>

        {/* ── Trust Badges Strip ────────────────────────────────────────── */}
        <div className="landing-badges-strip">
          <div className="landing-badge-item">
            <MessageSquare size={16} />
            <span>AI Chat for Business Docs</span>
          </div>
          <div className="landing-badge-item">
            <FolderSearch size={16} />
            <span>Local File Search & Indexing</span>
          </div>
          <div className="landing-badge-item">
            <Mic size={16} />
            <span>Voice Assistant</span>
          </div>
          <div className="landing-badge-item">
            <Users size={16} />
            <span>Multi-User Roles (Admin, Manager, Employee)</span>
          </div>
          <div className="landing-badge-item">
            <BarChart3 size={16} />
            <span>Reports & Analytics</span>
          </div>
        </div>

        {/* ── Interactive Live Product Showcase Mockup ────────────────── */}
        <div className="landing-mockup-wrapper" aria-label="Product Interface Demo">
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
                <CheckCircle2 size={12} /> Local Files Indexed
              </span>
            </div>
          </div>

          <div className="mockup-body">
            {/* Query selector pills */}
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
              <span style={{ fontSize: "12px", fontWeight: 700, color: "#64748b", textTransform: "uppercase" }}>
                Try These Examples:
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
                    {activeSample.fileType}
                  </span>
                </div>
                <span style={{ fontSize: "12px", color: "#64748b" }}>Results from your local files</span>
              </div>

              <p style={{ margin: "0 0 14px", fontSize: "14px", color: "#334155", lineHeight: 1.5 }}>
                {activeSample.summary}
              </p>

              {/* File Results Card */}
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
                  <span>📄 SOURCE DOCUMENT</span>
                  <span>🔒 Data Stays on Your PC</span>
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
                      <span>{previewExpanded ? "Hide Details" : "View Details"}</span>
                    </button>
                  </div>
                </div>

                {/* Expanded Preview */}
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
                        📊 Extracted Data (processed locally on your device):
                      </span>
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

      {/* ── Section: Key Features ─────────────────────────────────────── */}
      <section id="features" className="landing-section" aria-label="Features">
        <div className="landing-section-head">
          <span className="landing-eyebrow">What You Can Do With Nanvi AI</span>
          <h2 className="landing-section-title">Built for Real Business Work, Not Just Demos</h2>
          <p className="landing-section-sub">
            Nanvi AI connects to your actual business files on your Windows PC or company network.
            Ask questions in plain English and get answers with source citations from your own documents.
          </p>
        </div>

        <div className="landing-grid-4">
          <div className="landing-card">
            <div className="landing-card-icon">
              <Search size={22} />
            </div>
            <h3 className="landing-card-title">Search Your Company Files</h3>
            <p className="landing-card-desc">
              Point Nanvi to any folder on your PC — invoices, contracts, HR documents, project files.
              It indexes everything and lets you search by asking questions like
              "Find the cement bill from July" or "Show me all pending approvals."
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon">
              <FileSpreadsheet size={22} />
            </div>
            <h3 className="landing-card-title">Invoice & Payment Tracking</h3>
            <p className="landing-card-desc">
              Query thousands of invoices, purchase orders, and payment records instantly.
              Ask things like "How much do we owe to vendor X?" or "Which invoices are overdue by 90 days?"
              and get exact amounts with file references.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon">
              <FileText size={22} />
            </div>
            <h3 className="landing-card-title">Contract & Document Analysis</h3>
            <p className="landing-card-desc">
              Upload or index PDF contracts, agreements, and policy documents.
              Nanvi extracts key clauses, warranty terms, penalty conditions, and deadline dates
              so you don't have to read 50-page documents manually.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon">
              <BarChart3 size={22} />
            </div>
            <h3 className="landing-card-title">Reports & Analytics</h3>
            <p className="landing-card-desc">
              Generate summary reports from your data — aging analysis, vendor-wise breakdowns,
              department spending, and project cost tracking. Export to Excel or view directly
              in the app.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon">
              <Mic size={22} />
            </div>
            <h3 className="landing-card-title">Voice Assistant</h3>
            <p className="landing-card-desc">
              Speak your questions instead of typing. Nanvi's built-in voice mode lets you
              ask queries hands-free — useful when you're reviewing physical documents
              or on a call and need quick answers.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon">
              <Users size={22} />
            </div>
            <h3 className="landing-card-title">Team Roles & Access Control</h3>
            <p className="landing-card-desc">
              Set up your team with different access levels — Admin, Supervisor, Project Engineer,
              and Employee roles. Control who can see what data, manage users, and view audit logs
              of all queries made.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon">
              <Mail size={22} />
            </div>
            <h3 className="landing-card-title">Email Integration</h3>
            <p className="landing-card-desc">
              Connect your work email to search through correspondence alongside your documents.
              Find emails related to specific vendors, projects, or transactions without
              switching between applications.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon">
              <HardDrive size={22} />
            </div>
            <h3 className="landing-card-title">100% Private — Files Stay Local</h3>
            <p className="landing-card-desc">
              Your documents are never uploaded to any cloud server. All file indexing
              and search happens on your own computer. Only your typed questions go to the AI —
              not your actual files. Complete data privacy by design.
            </p>
          </div>
        </div>
      </section>

      {/* ── Section: How It Works ─────────────────────────────────────── */}
      <section id="how-it-works" className="landing-section" aria-label="How It Works">
        <div className="landing-section-head">
          <span className="landing-eyebrow">Getting Started</span>
          <h2 className="landing-section-title">Start Querying Your Business Data in 3 Minutes</h2>
          <p className="landing-section-sub">
            Install from the Microsoft Store, point to your company folder, and start asking questions.
            No complex setup. No cloud configuration.
          </p>
        </div>

        <div className="landing-steps-row">
          <div className="landing-step-card">
            <span className="step-num-badge">1</span>
            <h3 className="step-card-title">Install from Microsoft Store</h3>
            <p className="step-card-desc">
              Search "<strong>Nanvi AI Enterprise Assistant</strong>" in the Microsoft Store
              or click the download button above. Installs in one click — no warnings,
              no admin permissions needed. Works on Windows 10 and 11.
            </p>
          </div>

          <div className="landing-step-card">
            <span className="step-num-badge">2</span>
            <h3 className="step-card-title">Select Your Company Folder</h3>
            <p className="step-card-desc">
              Point Nanvi to the folder where your business files are stored — 
              <code>C:\CompanyData</code>, network drives, or any folder with your invoices,
              contracts, and documents. Nanvi indexes them locally on your machine.
            </p>
          </div>

          <div className="landing-step-card">
            <span className="step-num-badge">3</span>
            <h3 className="step-card-title">Ask Questions, Get Answers</h3>
            <p className="step-card-desc">
              Type or speak your question in plain English. Nanvi searches your files,
              extracts the relevant data, and shows you the answer with a direct link
              to the source document. Click to open in Excel, Word, or your default app.
            </p>
          </div>
        </div>
      </section>

      {/* ── Section: Web vs Desktop ───────────────────────────────────── */}
      <section id="architecture" className="landing-section" style={{ background: "#f1f5f9", borderRadius: "20px" }}>
        <div className="landing-section-head">
          <span className="landing-eyebrow">Two Ways to Use Nanvi AI</span>
          <h2 className="landing-section-title">Desktop App for Local Files, Web App for Remote Access</h2>
          <p className="landing-section-sub">
            Use the Windows desktop app when you need to search files stored on your local computer.
            Use the web app when you're away from your workstation or need browser-only access.
          </p>
        </div>

        <div className="landing-arch-grid">
          {/* Desktop Application Card */}
          <div className="arch-card featured">
            <span className="arch-badge-ribbon">Desktop App — Microsoft Store</span>
            <div className="arch-card-header">
              <div className="arch-icon">
                <Laptop size={26} />
              </div>
              <h3 className="arch-card-title">Windows Desktop Application</h3>
              <p className="arch-card-desc">
                Full Windows app that runs on your PC. Indexes your local files and lets
                you query them with AI. No files are uploaded to the cloud.
              </p>
            </div>

            <ul className="arch-feature-list">
              <li className="arch-feature-item">
                <CheckCircle2 size={16} />
                <span>Install from Microsoft Store — verified, no security warnings</span>
              </li>
              <li className="arch-feature-item">
                <CheckCircle2 size={16} />
                <span>Index local folders: invoices, contracts, HR docs, project files</span>
              </li>
              <li className="arch-feature-item">
                <CheckCircle2 size={16} />
                <span>Open results directly in Excel, Word, Acrobat with one click</span>
              </li>
              <li className="arch-feature-item">
                <CheckCircle2 size={16} />
                <span>Voice assistant — ask questions by speaking</span>
              </li>
              <li className="arch-feature-item">
                <CheckCircle2 size={16} />
                <span>Works offline for indexed files — no internet required after setup</span>
              </li>
            </ul>

            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              <a
                href={MS_STORE_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-landing-primary"
                style={{ width: "100%", justifyContent: "center", textDecoration: "none" }}
              >
                <Store size={16} />
                <span>Get from Microsoft Store (Recommended)</span>
              </a>
              <button
                type="button"
                onClick={() => setShowExeWarning(!showExeWarning)}
                style={{
                  background: "none",
                  border: "none",
                  color: "#64748b",
                  fontSize: "12.5px",
                  fontWeight: 500,
                  cursor: "pointer",
                  textDecoration: "underline",
                  padding: "4px",
                }}
              >
                Or download .exe installer (advanced users)
              </button>
              {showExeWarning && (
                <div
                  style={{
                    background: "#fffbeb",
                    border: "1px solid #fcd34d",
                    borderRadius: "8px",
                    padding: "12px",
                    fontSize: "13px",
                    color: "#92400e",
                    display: "flex",
                    gap: "8px",
                    alignItems: "flex-start",
                  }}
                >
                  <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: "2px" }} />
                  <div>
                    <strong>Windows Smart App Control may block the .exe installer</strong> because it is
                    not code-signed. You may need to click "More info" → "Run anyway" to proceed.
                    For a hassle-free experience, use the Microsoft Store version above.
                    <br />
                    <button
                      type="button"
                      onClick={() => handleDownload("exe")}
                      disabled={downloading}
                      style={{
                        marginTop: "8px",
                        background: "#f59e0b",
                        color: "#ffffff",
                        border: "none",
                        borderRadius: "6px",
                        padding: "6px 14px",
                        fontSize: "12px",
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                    >
                      <Download size={12} /> {downloading ? "Downloading..." : "Download .exe Anyway"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Cloud Web Service Card */}
          <div className="arch-card">
            <span className="arch-badge-ribbon" style={{ background: "#eff6ff", color: "#1e40af", borderColor: "#bfdbfe" }}>
              Web App — Zero Install
            </span>
            <div className="arch-card-header">
              <div className="arch-icon" style={{ background: "#eff6ff", color: "#2563eb" }}>
                <Globe size={26} />
              </div>
              <h3 className="arch-card-title">Cloud Web Application</h3>
              <p className="arch-card-desc">
                Access Nanvi AI from any browser — no installation needed. Ideal for teams working
                remotely or managers who need quick access from any device.
              </p>
            </div>

            <ul className="arch-feature-list">
              <li className="arch-feature-item">
                <CheckCircle2 size={16} />
                <span>Works on any device with a modern web browser</span>
              </li>
              <li className="arch-feature-item">
                <CheckCircle2 size={16} />
                <span>Role-based access: Admin, Supervisor, Project Engineer, Employee</span>
              </li>
              <li className="arch-feature-item">
                <CheckCircle2 size={16} />
                <span>Full chat history, audit logs, and query export</span>
              </li>
              <li className="arch-feature-item">
                <CheckCircle2 size={16} />
                <span>Admin dashboard with user management and analytics</span>
              </li>
              <li className="arch-feature-item">
                <CheckCircle2 size={16} />
                <span>No installation — just sign in and start asking</span>
              </li>
            </ul>

            <button
              type="button"
              className="btn-landing-secondary"
              onClick={onLaunchWebApp}
              style={{ width: "100%", justifyContent: "center" }}
            >
              <ExternalLink size={16} />
              <span>Open Web App</span>
            </button>
          </div>
        </div>
      </section>

      {/* ── Section: Who Uses Nanvi AI ────────────────────────────────── */}
      <section className="landing-section" aria-label="Use Cases">
        <div className="landing-section-head">
          <span className="landing-eyebrow">Who Is This For</span>
          <h2 className="landing-section-title">Built for Teams That Work With Documents Daily</h2>
          <p className="landing-section-sub">
            If your team spends time searching for invoices, reading contracts, or tracking payments
            across spreadsheets — Nanvi AI saves hours every week.
          </p>
        </div>

        <div className="landing-grid-4">
          <div className="landing-card">
            <div className="landing-card-icon" style={{ background: "#eff6ff", color: "#2563eb" }}>
              <BarChart3 size={22} />
            </div>
            <h3 className="landing-card-title">Accounts & Finance Teams</h3>
            <p className="landing-card-desc">
              Track pending payments, search vendor invoices, generate aging reports,
              and verify tax amounts across thousands of records — all by asking in plain English.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon" style={{ background: "#fef3c7", color: "#d97706" }}>
              <FileText size={22} />
            </div>
            <h3 className="landing-card-title">Legal & Contract Teams</h3>
            <p className="landing-card-desc">
              Search contract clauses, extract warranty periods, find penalty terms,
              and compare agreement conditions across multiple documents without reading each one.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon" style={{ background: "#f0fdf4", color: "#16a34a" }}>
              <Settings size={22} />
            </div>
            <h3 className="landing-card-title">Project Managers</h3>
            <p className="landing-card-desc">
              Find project documents, track material purchase orders, check work orders
              and site reports. Get quick summaries from project folders without opening dozens of files.
            </p>
          </div>

          <div className="landing-card">
            <div className="landing-card-icon" style={{ background: "#fdf2f8", color: "#db2777" }}>
              <Shield size={22} />
            </div>
            <h3 className="landing-card-title">IT & Admin Teams</h3>
            <p className="landing-card-desc">
              Manage user access, view audit logs of all queries, set up role-based permissions,
              and ensure sensitive documents are only accessible to authorized team members.
            </p>
          </div>
        </div>
      </section>

      {/* ── Section: Download Center ──────────────────────────────────── */}
      <section id="downloads" className="landing-section" aria-label="Download Center">
        <div className="download-center-banner">
          <div className="download-banner-left">
            <h2>Get Nanvi AI for Your Team</h2>
            <p>
              Install the desktop app from the Microsoft Store for the smoothest experience,
              or launch the web version directly in your browser — no download needed.
            </p>

            <div className="download-banner-actions">
              <a
                href={MS_STORE_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-landing-primary"
                style={{ background: "#ffffff", color: "#0f172a", textDecoration: "none" }}
              >
                <Store size={18} className="text-teal-800" />
                <span style={{ color: "#0f172a" }}>Get from Microsoft Store</span>
              </a>

              <button
                type="button"
                className="btn-landing-secondary"
                onClick={onLaunchWebApp}
                style={{ background: "rgba(255, 255, 255, 0.15)", color: "#ffffff !important", borderColor: "rgba(255, 255, 255, 0.3)" }}
              >
                <Globe size={18} />
                <span style={{ color: "#ffffff" }}>Launch Web App</span>
              </button>
            </div>

            <div style={{ marginTop: "18px", fontSize: "13px", color: "#94a3b8" }}>
              Available on Windows 10/11 via Microsoft Store. Web app works on all devices.
            </div>
          </div>

          <div className="download-banner-right">
            <h4>Quick Start Guide:</h4>
            <ul className="download-steps-mini">
              <li>
                <CheckCircle2 size={16} className="text-green-400" />
                <span>1. Install from Microsoft Store (or download .exe)</span>
              </li>
              <li>
                <CheckCircle2 size={16} className="text-green-400" />
                <span>2. Sign in with your company credentials</span>
              </li>
              <li>
                <CheckCircle2 size={16} className="text-green-400" />
                <span>3. Select your business folder to index</span>
              </li>
              <li>
                <CheckCircle2 size={16} className="text-green-400" />
                <span>4. Ask questions about your documents</span>
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
            <a
              href={MS_STORE_URL}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: "#006583", fontWeight: 600, textDecoration: "none", fontSize: "13px" }}
            >
              Microsoft Store
            </a>
            <span>•</span>
            <button
              type="button"
              onClick={onLaunchWebApp}
              style={{ background: "none", border: "none", color: "#006583", fontWeight: 600, cursor: "pointer", textDecoration: "underline" }}
            >
              Sign In to Web Portal
            </button>
            <span>•</span>
            <span>Windows 10/11 & Web</span>
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
